# water_log_tui.py

import sys
import sqlite3

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Header, Footer, Button, Static

from textual_plotext import PlotextPlot  # <--- NEW

from sqlite_water_tracker.ensure_db import ensure_db, DEFAULT_WEIGHT_LBS  # noqa: E402


class WaterLogApp(App):
    """TUI to show latest water entries, daily totals, and rolling 24h stats."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-content {
        height: 1fr;
        layout: vertical;
        padding: 1;
    }

    #controls {
        height: 3;
        layout: horizontal;
        padding: 0 1;
    }

    #controls Button {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "reload", "Reload"),
        ("1", "drink_water", "Drink Water"),
        ("2", "next_view", "Next View"),
    ]

    def __init__(self, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path

        # 0 = rolling table, 1 = log table, 2 = full table, 3 = rolling chart
        self.current_view = 0

        self.log_table = DataTable(zebra_stripes=True, id="log-table")
        self.full_table = DataTable(zebra_stripes=True, id="full-table")
        self.rolling_table = DataTable(zebra_stripes=True, id="rolling-table")

        # Make the log table about 20 terminal rows tall and scrollable
        self.log_table.cursor_type = "row"
        self.log_table.styles.height = 20

        # Plotext-based chart for the rolling 24h view
        self.rolling_plot = PlotextPlot(id="rolling-plot")
        self.rolling_plot.styles.height = 30  # tweak as desired

        # Summary "card" for last 24h info
        self.summary_view = Static(id="summary-view")
        self.summary_view.styles.height = 5  # small card-like block

    def compose(self) -> ComposeResult:
        # Clock off
        yield Header(show_clock=False)

        with VerticalScroll(id="main-content"):
            # One title, updated when rotating views
            yield Static("Rolling 24h", classes="section-title", id="section-title")

            # All tables + plot are in the layout; we toggle visibility via .display
            yield self.rolling_table
            yield self.log_table
            yield self.full_table
            yield self.rolling_plot
            yield self.summary_view

        with Horizontal(id="controls"):
            # View-rotation button
            # yield Button("View: Latest Drinks", id="rotate-view-btn")
            yield Button("next", id="rotate-view-btn")
            # yield Button("Delete Selected", id="delete-row-btn")
            yield Button("Drink Water", id="drink-water-btn")
            yield Button("Del", id="delete-row-btn")

        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all()
        # Start on rolling table view
        self._show_view(0)

    def _drink_water(self) -> None:
        """Log a standard drink and refresh the views."""
        self.insert_drink(8.0)
        self.refresh_all()
        self._show_view(self.current_view)

    def action_reload(self) -> None:
        self.refresh_all()
        self._show_view(self.current_view)

    def action_drink_water(self) -> None:
        self._drink_water()

    def action_next_view(self) -> None:
        """Cycle to the next view."""
        self._show_view(self.current_view + 1)

    # --- DB helpers -----------------------------------------------------

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def insert_drink(self, ounces: float = 8.0) -> None:
        """Insert a new drink entry into water_log."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO water_log (timestamp, ounces)
                VALUES (datetime('now', 'localtime'), ?)
                """,
                (ounces,),
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_log_rows(self):
        """Latest individual entries from water_log."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, timestamp, ounces
                FROM water_log
                ORDER BY timestamp DESC
                LIMIT 200
                """
            )
            return cur.fetchall()
        finally:
            conn.close()

    def fetch_full_rows(self):
        """Latest daily summary rows from water_log_full."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT date, total, weight, target, percent_of_target
                FROM water_log_full
                ORDER BY date DESC
                LIMIT 10
                """
            )
            return cur.fetchall()
        finally:
            conn.close()

    def fetch_rolling_rows(self):
        """Latest rolling 24h rows from rolling_log_full."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT timestamp,
                       ounces,
                       rolling_24h_ounces,
                       weight,
                       target,
                       percent_of_target
                FROM rolling_log_full
                ORDER BY timestamp DESC
                LIMIT 20
                """
            )
            return cur.fetchall()
        finally:
            conn.close()

    def fetch_last_24h_summary(self):
        """Fetch single-row summary from last_24_hours_summary view."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT total_ounces_last_24_hours,
                       weight,
                       target_ounces,
                       percent_of_target
                FROM last_24_hours_summary
                LIMIT 1
                """
            )
            return cur.fetchone()
        finally:
            conn.close()

    def delete_selected_log_row(self) -> None:
        """Delete the selected row from water_log when in the log view."""
        # Only act in the water_log view (view index 1)
        if self.current_view != 1:
            return

        # Get current cursor row in the DataTable
        row_index = self.log_table.cursor_row
        if row_index is None:
            return  # nothing selected

        # Get row data from the table (first column is the id)
        row = self.log_table.get_row_at(row_index)
        if not row:
            return

        row_id_str = row[0]
        try:
            row_id = int(row_id_str)
        except (TypeError, ValueError):
            return

        # Delete from DB
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM water_log WHERE id = ?", (row_id,))
            conn.commit()
        finally:
            conn.close()

        # Refresh anything that depends on water_log
        self.refresh_log_table()
        self.refresh_rolling_table()
        self.refresh_rolling_plot()
        self.refresh_summary_view()

        # Stay in the same view
        self._show_view(self.current_view)



    # --- Table & plot refreshers ---------------------------------------

    def refresh_all(self) -> None:
        self.refresh_log_table()
        self.refresh_full_table()
        self.refresh_rolling_table()
        self.refresh_rolling_plot()
        self.refresh_summary_view()

    def refresh_log_table(self) -> None:
        """Populate the per-entry table."""
        self.log_table.clear(columns=True)
        self.log_table.add_columns("id", "timestamp", "ounces")

        rows = self.fetch_log_rows()
        for row in rows:
            self.log_table.add_row(str(row[0]), row[1], str(row[2]))

    def refresh_full_table(self) -> None:
        """Populate the daily summary table."""
        self.full_table.clear(columns=True)
        self.full_table.add_columns(
            "date", "total", "weight", "target", "% of target"
        )

        rows = self.fetch_full_rows()
        for row in rows:
            # row = (date, total, weight, target, percent_of_target)
            self.full_table.add_row(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
            )

    def refresh_rolling_table(self) -> None:
        """Populate the rolling 24h table."""
        self.rolling_table.clear(columns=True)
        self.rolling_table.add_columns(
            "timestamp",
            "oz",
            "24h",
            "% of target",
        )

        rows = self.fetch_rolling_rows()
        for row in rows:
            # row = (timestamp, ounces, rolling_24h_ounces, weight, target, percent_of_target)
            self.rolling_table.add_row(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[5]),
            )

    # def refresh_rolling_plot(self) -> None:
    #     """Build a Plotext line chart of rolling_24h_ounces."""
    #     rows = self.fetch_rolling_rows()
    #     plt = self.rolling_plot.plt

    #     # Clear any previous plot
    #     plt.clear_plot()

    #     if not rows:
    #         plt.title("Rolling 24h (no data)")
    #         return

    #     # Oldest on the left, newest on the right
    #     rows = list(reversed(rows))
    #     y = [float(r[2]) for r in rows]  # rolling_24h_ounces
    #     x = list(range(len(y)))

    #     # Simple line plot
    #     plt.plot(x, y)
    #     plt.title("Rolling 24h (oz)")
    #     plt.xlabel("Entry (oldest → newest)")
    #     plt.ylabel("24h total (oz)")
    #     plt.grid(True, True)


    def refresh_rolling_plot(self) -> None:
        """Build a Plotext line chart of rolling_24h_ounces."""
        rows = self.fetch_rolling_rows()
        plt = self.rolling_plot.plt

        # Try to clear any previous plot safely
        for name in ("clear_figure", "clear_plot", "clear_data"):
            clear = getattr(plt, name, None)
            if callable(clear):
                clear()
                break

        if not rows:
            plt.title("Rolling 24h (no data)")
            return

        # Oldest on the left, newest on the right
        # rows = list(reversed(rows))
        # y = [float(r[2]) for r in rows]  # rolling_24h_ounces
        y = [float(r[5]) for r in rows]  # rolling_24h_ounces
        x = list(range(len(y)))

        # plt.plot(x, y)
        # plt.bar(x, y)  # Using bar plot for better visibility
        plt.bar(x, y, orientation="horizontal")
        plt.title("Rolling 24h (oz)")
        plt.xlabel("Entry (oldest → newest)")
        plt.ylabel("24h total (oz)")
        # plt.grid(True, True)

    # def refresh_summary_view(self) -> None:
    #     """Update the last-24-hours summary view."""
    #     row = self.fetch_last_24h_summary()

    #     if not row:
    #         self.summary_view.update("No summary data available.")
    #         return

    #     total_oz, weight, target_oz, percent = row

    #     text = (
    #         f"Last 24 hours\n"
    #         f"  Total:  {total_oz:.1f} oz\n"
    #         f"  Target: {target_oz:.1f} oz  ({percent:.1f}% of target)\n"
    #         f"  Weight: {weight:.1f} lbs"
    #     )

    #     self.summary_view.update(text)



    def refresh_summary_view(self) -> None:
        """Update the last-24-hours summary view."""
        row = self.fetch_last_24h_summary()

        if not row:
            self.summary_view.update("No summary data available.")
            return

        total_oz, weight, target_oz, percent = row

        total_oz = 0.0 if total_oz is None else float(total_oz)
        weight = DEFAULT_WEIGHT_LBS if weight is None else float(weight)
        target_oz = 0.0 if target_oz is None else float(target_oz)
        percent = 0.0 if percent is None else float(percent)

        text = (
            f"Last 24 hours\n"
            f"  Total:  {total_oz:.1f} oz\n"
            f"  Target: {target_oz:.1f} oz  ({percent:.1f}% of target)\n"
            f"  Weight: {weight:.1f} lbs"
        )

        if total_oz <= 0:
            text += "\n  No drinks logged in the last 24 hours."

        self.summary_view.update(text)



    # --- View switching -------------------------------------------------

    # def _show_view(self, index: int) -> None:
    #     """Show one of the four views based on index 0–3."""
    #     self.current_view = index % 4

    #     title_widget = self.query_one("#section-title", Static)
    #     rotate_button = self.query_one("#rotate-view-btn", Button)

    #     if self.current_view == 0:
    #         # Rolling 24h table
    #         self.rolling_table.display = True
    #         self.log_table.display = False
    #         self.full_table.display = False
    #         self.rolling_plot.display = False

    #         title_widget.update("Rolling 24h")
    #         rotate_button.label = "View: Latest Drinks"

    #     elif self.current_view == 1:
    #         # Latest Drinks (water_log)
    #         self.rolling_table.display = False
    #         self.log_table.display = True
    #         self.full_table.display = False
    #         self.rolling_plot.display = False

    #         title_widget.update("Latest Drinks (water_log)")
    #         rotate_button.label = "View: Daily Totals"

    #         # Focus so you can scroll immediately
    #         self.log_table.focus()

    #     elif self.current_view == 2:
    #         # Daily Totals (water_log_full)
    #         self.rolling_table.display = False
    #         self.log_table.display = False
    #         self.full_table.display = True
    #         self.rolling_plot.display = False

    #         title_widget.update("Daily Totals (water_log_full)")
    #         rotate_button.label = "View: Rolling Chart"

    #     else:
    #         # Rolling 24h chart view (Plotext)
    #         self.rolling_table.display = False
    #         self.log_table.display = False
    #         self.full_table.display = False
    #         self.rolling_plot.display = True

    #         title_widget.update("Rolling 24h Chart")
    #         rotate_button.label = "View: Rolling 24h"

    # def _show_view(self, index: int) -> None:
    #     """Show one of the five views based on index 0–4."""
    #     self.current_view = index % 5

    #     title_widget = self.query_one("#section-title", Static)
    #     rotate_button = self.query_one("#rotate-view-btn", Button)

    #     if self.current_view == 0:
    #         # Rolling 24h table
    #         self.rolling_table.display = True
    #         self.log_table.display = False
    #         self.full_table.display = False
    #         self.rolling_plot.display = False
    #         self.summary_view.display = False

    #         title_widget.update("Rolling 24h")
    #         rotate_button.label = "View: Latest Drinks"

    #     elif self.current_view == 1:
    #         # Latest Drinks (water_log)
    #         self.rolling_table.display = False
    #         self.log_table.display = True
    #         self.full_table.display = False
    #         self.rolling_plot.display = False
    #         self.summary_view.display = False

    #         title_widget.update("Latest Drinks (water_log)")
    #         rotate_button.label = "View: Daily Totals"
    #         self.log_table.focus()

    #     elif self.current_view == 2:
    #         # Daily Totals (water_log_full)
    #         self.rolling_table.display = False
    #         self.log_table.display = False
    #         self.full_table.display = True
    #         self.rolling_plot.display = False
    #         self.summary_view.display = False

    #         title_widget.update("Daily Totals (water_log_full)")
    #         rotate_button.label = "View: Rolling Chart"

    #     elif self.current_view == 3:
    #         # Rolling 24h chart view (Plotext)
    #         self.rolling_table.display = False
    #         self.log_table.display = False
    #         self.full_table.display = False
    #         self.rolling_plot.display = True
    #         self.summary_view.display = False

    #         title_widget.update("Rolling 24h Chart")
    #         rotate_button.label = "View: 24h Summary"

    #     else:
    #         # Last 24 hours summary card
    #         self.rolling_table.display = False
    #         self.log_table.display = False
    #         self.full_table.display = False
    #         self.rolling_plot.display = False
    #         self.summary_view.display = True

    #         title_widget.update("Last 24 Hours Summary")
    #         rotate_button.label = "View: Rolling 24h"


    def _show_view(self, index: int) -> None:
        """Show one of the five views based on index 0–4."""
        self.current_view = index % 5

        title_widget = self.query_one("#section-title", Static)
        rotate_button = self.query_one("#rotate-view-btn", Button)
        delete_button = self.query_one("#delete-row-btn", Button)  # NEW

        if self.current_view == 0:
            # Rolling 24h table
            self.rolling_table.display = True
            self.log_table.display = False
            self.full_table.display = False
            self.rolling_plot.display = False
            # self.summary_view.display = False
            self.summary_view.display = True

            delete_button.display = False  # hide here

            title_widget.update("Rolling 24h")
            # rotate_button.label = "View: Latest Drinks"
            rotate_button.label = "next"

        elif self.current_view == 1:
            # Latest Drinks (water_log)
            self.rolling_table.display = False
            self.log_table.display = True
            self.full_table.display = False
            self.rolling_plot.display = False
            self.summary_view.display = True

            delete_button.display = True  # show in this view

            title_widget.update("Latest Drinks (water_log)")
            # rotate_button.label = "View: Daily Totals"
            rotate_button.label = "next"

            self.log_table.focus()

        elif self.current_view == 2:
            # Daily Totals (water_log_full)
            self.rolling_table.display = False
            self.log_table.display = False
            self.full_table.display = True
            self.rolling_plot.display = False
            self.summary_view.display = True

            delete_button.display = False

            title_widget.update("Daily Totals (water_log_full)")
            # rotate_button.label = "View: Rolling Chart"
            rotate_button.label = "next"

        elif self.current_view == 3:
            # Rolling 24h chart view (Plotext)
            self.rolling_table.display = False
            self.log_table.display = False
            self.full_table.display = False
            self.rolling_plot.display = True
            self.summary_view.display = True

            delete_button.display = False

            title_widget.update("Rolling 24h Chart")
            # rotate_button.label = "View: 24h Summary"
            rotate_button.label = "next"

        else:
            # Last 24 hours summary card
            self.rolling_table.display = False
            self.log_table.display = False
            self.full_table.display = False
            self.rolling_plot.display = False
            self.summary_view.display = True

            delete_button.display = False

            title_widget.update("Last 24 Hours Summary")
            # rotate_button.label = "View: Rolling 24h"
            rotate_button.label = "next"


    # --- Events ---------------------------------------------------------

    # def on_button_pressed(self, event: Button.Pressed) -> None:
    #     """Handle button presses."""
    #     if event.button.id == "drink-water-btn":
    #         self.insert_drink(8.0)
    #         self.refresh_all()
    #         self._show_view(self.current_view)
    #     elif event.button.id == "rotate-view-btn":
    #         # Cycle: rolling table -> log table -> full table -> chart -> rolling table
    #         self._show_view(self.current_view + 1)

    # def on_button_pressed(self, event: Button.Pressed) -> None:
    #     """Handle button presses."""
    #     if event.button.id == "drink-water-btn":
    #         self.insert_drink(8.0)
    #         self.refresh_all()
    #         self._show_view(self.current_view)
    #     elif event.button.id == "rotate-view-btn":
    #         # Cycle: rolling table -> log -> full -> chart -> summary -> rolling
    #         self._show_view(self.current_view + 1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "drink-water-btn":
            self._drink_water()

        elif event.button.id == "rotate-view-btn":
            # Cycle: rolling table -> log -> full -> chart -> summary -> rolling
            self.action_next_view()

        elif event.button.id == "delete-row-btn":
            self.delete_selected_log_row()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "sqlite-water-tracker.db"
    ensure_db(db_path)
    app = WaterLogApp(db_path)
    app.run()
