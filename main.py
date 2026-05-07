import os
import sys
import ctypes

# Ensure the app's own directory is on sys.path so 'kivymd' is found
sys.path.append(os.path.dirname(__file__))
os.environ.setdefault("KIVY_CLIPBOARD", "sdl2")

from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.factory import Factory
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivy.core.window import Window

from kivy.properties import (
    ListProperty,
    NumericProperty,
    StringProperty,
    BooleanProperty,
)
from kivy.uix.boxlayout import BoxLayout

import os
import platform  # for OS name

from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.scrollview import ScrollView
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.textfield import MDTextField

from computer_player import handle_computer_turn  # AI helper
from online_players import (get_online_players, get_online_players_async,
                            is_name_taken, suggest_name, register_player)

ROWS = 6
COLS = 7
WIN_LEN = 5
ADMOB_INTERSTITIAL_AD_UNIT_ID = "ca-app-pub-4692752434992586/7652208008"

_admob_bridge = None
_admob_unavailable = False


def _get_admob_bridge():
    """Return exported native iOS AdMob bridge functions when running on iOS."""
    global _admob_bridge, _admob_unavailable
    if _admob_unavailable:
        return None
    if _admob_bridge is not None:
        return _admob_bridge
    if sys.platform != "ios" and os.environ.get("KIVY_BUILD") != "ios":
        _admob_unavailable = True
        return None
    try:
        bridge = ctypes.CDLL(None)
        bridge.AdMobConfigureInterstitial.argtypes = [ctypes.c_char_p]
        bridge.AdMobConfigureInterstitial.restype = None
        bridge.AdMobShowInterstitialAfterDelay.argtypes = [ctypes.c_double]
        bridge.AdMobShowInterstitialAfterDelay.restype = None
        _admob_bridge = bridge
    except Exception as exc:
        print(f"AdMob unavailable: {exc}")
        _admob_unavailable = True
        return None
    return _admob_bridge


def initialize_admob():
    bridge = _get_admob_bridge()
    if bridge:
        bridge.AdMobConfigureInterstitial(
            ADMOB_INTERSTITIAL_AD_UNIT_ID.encode("utf-8")
        )


def show_interstitial_after_game(delay_seconds=1.0):
    bridge = _get_admob_bridge()
    if bridge:
        bridge.AdMobShowInterstitialAfterDelay(float(delay_seconds))


class NamePickerContent(MDBoxLayout):
    """Content widget shown inside the first-launch name-picker dialog."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(8)
        self.size_hint_y = None
        self.height = dp(100)
        self.padding = [dp(8), dp(4), dp(8), dp(0)]

        self.name_field = MDTextField(
            hint_text="Enter your display name",
            mode="fill",
        )
        self.info_label = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=(0.85, 0.25, 0.1, 1),
            font_style="Caption",
            size_hint_y=None,
            height=dp(20),
        )
        self.add_widget(self.name_field)
        self.add_widget(self.info_label)

# Colors for the pieces (r, g, b, a)
EMPTY_COLOR   = (0.18, 0.35, 0.9, 1)  # default blue-ish hole color
P1_COLOR      = (0.95, 0.2,  0.2, 1)  # player 1: red (computer)
P2_COLOR      = (0.1,  0.9,  0.2, 1)  # player 2: green (human)
LAST_P1_COLOR = (1.0,  0.45, 0.0, 1)  # last computer move: bright orange
LAST_P2_COLOR = (0.0,  0.85, 0.9, 1)  # last player move: cyan


class GameState(BoxLayout):
    board = ListProperty()                # 6x7 ints: 0 empty, 1 P1, 2 P2
    current_player = NumericProperty(1)
    status_text = StringProperty("")
    game_over = BooleanProperty(False)
    winning_cells = ListProperty([])      # list of (row, col) tuples
    last_move = ListProperty([-1, -1])    # (row, col) of the most recent drop
    game_mode = StringProperty("os")      # "os" or "online"

    # Scores
    p1_score = NumericProperty(0)
    p2_score = NumericProperty(0)

    # Player names
    p1_name = StringProperty("")
    p2_name = StringProperty("Player 2")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Build an OS name like "macOS 15.0", then take the first word
        os_full = f"{platform.system()} {platform.release()}".strip()
        first_word = os_full.split()[0] if os_full else "Computer"
        self.p1_name = first_word or "Computer"
        self.p2_name = "Player 2"
        self.reset_game()

    def reset_game(self):
        # Do NOT reset scores here, scores persist across games
        self.board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.current_player = 1
        self.game_over = False
        self.winning_cells = []
        self.last_move = [-1, -1]
        self.status_text = f"{self.p1_name}'s turn (Red)"

    def play_move(self, col: int):
        if self.game_over:
            return False, None, None, False, False

        if not (0 <= col < COLS):
            return False, None, None, False, False

        # Find lowest empty row in column
        for row in range(ROWS - 1, -1, -1):
            if self.board[row][col] == 0:
                self.board[row][col] = self.current_player

                self.last_move = [row, col]
                won, win_cells = self.check_win(row, col)
                draw = self.check_draw()

                if won:
                    self.game_over = True
                    self.winning_cells = win_cells
                    # scoring: winner gets 2 points
                    if self.current_player == 1:
                        self.p1_score += 2
                        winner_name = self.p1_name
                    else:
                        self.p2_score += 2
                        winner_name = self.p2_name
                    self.status_text = f"{winner_name} wins!"
                elif draw:
                    self.game_over = True
                    # scoring: both get 1 point on draw
                    self.p1_score += 1
                    self.p2_score += 1
                    self.status_text = "Draw game."
                else:
                    self.current_player = 2 if self.current_player == 1 else 1
                    if self.current_player == 1:
                        self.status_text = f"{self.p1_name}'s turn (Red)"
                    else:
                        self.status_text = f"{self.p2_name}'s turn (Green)"

                return True, row, col, won, draw

        # Column full
        return False, None, None, False, False

    def check_draw(self) -> bool:
        for r in range(ROWS):
            for c in range(COLS):
                if self.board[r][c] == 0:
                    return False
        return True

    def check_win(self, row: int, col: int):
        player = self.board[row][col]
        if player == 0:
            return False, []

        directions = [
            (1, 0),   # vertical
            (0, 1),   # horizontal
            (1, 1),   # diag down-right
            (1, -1),  # diag down-left
        ]

        winning_cells = []
        seen = set()

        for dr, dc in directions:
            cells = [(row, col)]

            # Forward direction
            r, c = row + dr, col + dc
            while 0 <= r < ROWS and 0 <= c < COLS and self.board[r][c] == player:
                cells.append((r, c))
                r += dr
                c += dc

            # Backward direction
            r, c = row - dr, col - dc
            while 0 <= r < ROWS and 0 <= c < COLS and self.board[r][c] == player:
                cells.insert(0, (r, c))
                r -= dr
                c -= dc

            if len(cells) >= WIN_LEN:
                for cell in cells:
                    if cell not in seen:
                        seen.add(cell)
                        winning_cells.append(cell)

        return bool(winning_cells), winning_cells


class BoardCell(ButtonBehavior, Widget):
    """Board hole widget — properties declared here so iOS canvas bindings fire."""
    md_bg_color  = ListProperty([0.18, 0.35, 0.9, 1])
    row          = NumericProperty(0)
    col          = NumericProperty(0)
    is_winning   = BooleanProperty(False)
    is_last_move = BooleanProperty(False)
    player       = NumericProperty(0)


class DraggableCoin(ButtonBehavior, Widget):
    player = NumericProperty(1)        # 1 = red, 2 = green
    dragging = BooleanProperty(False)
    start_pos = ListProperty([0, 0])   # original position to snap back
    star_color = ListProperty([0.1, 0.9, 0.2, 1])

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
            self.start_pos = self.pos[:]
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.dragging and touch.grab_current is self:
            self.center_x, self.center_y = touch.pos
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.dragging and touch.grab_current is self:
            touch.ungrab(self)
            self.dragging = False
            root = MDApp.get_running_app().root
            if hasattr(root, "on_coin_drop"):
                root.on_coin_drop(self.player, *touch.pos, self)
            # we return True because we handled this touch
            return True
        return super().on_touch_up(touch)


class GameScreen(BoxLayout):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_resize=self._on_resize)
        Clock.schedule_once(self._post_init, 0)

    def _on_resize(self, window, width, height):
        self._apply_orientation(width, height)
        self.update_board_from_state()
        self._refresh_leaderboard()

    def _apply_orientation(self, width, height):
        main_area    = self.ids.get("main_area")
        side_panel   = self.ids.get("side_panel")
        coins_leader = self.ids.get("coins_leader_layout")
        coins_row    = self.ids.get("coins_row")
        if not main_area or not side_panel:
            return
        if width >= height:
            # Landscape: board left (70%), side panel right (30%)
            self.orientation        = "horizontal"
            self.spacing            = dp(4)
            self.padding            = [dp(4), dp(4), dp(4), dp(4)]
            main_area.size_hint_x   = 0.70
            main_area.size_hint_y   = 1
            main_area.height        = 0
            main_area.spacing       = dp(4)
            main_area.padding       = [dp(4), dp(4), dp(4), dp(4)]
            side_panel.size_hint_x  = 0.30
            side_panel.size_hint_y  = 1
            side_panel.height       = 0
            side_panel.padding      = [dp(6), dp(6), dp(6), dp(6)]
            side_panel.spacing      = dp(6)
            if coins_leader:
                coins_leader.orientation = "vertical"
                coins_leader.size_hint_y = 1
                coins_leader.spacing = dp(6)
            if coins_row:
                coins_row.size_hint_x = 1
                coins_row.size_hint_y = None
                coins_row.height      = dp(80)
        else:
            # Portrait: side panel is fixed height, board fills all remaining space
            self.orientation        = "vertical"
            self.spacing            = 0
            self.padding            = [dp(4), dp(4), dp(4), 0]
            main_area.size_hint_x   = 1
            main_area.size_hint_y   = 1          # fill everything above side panel
            main_area.spacing       = 0
            main_area.padding       = [dp(4), dp(4), dp(4), 0]
            side_panel.size_hint_x  = 1
            side_panel.size_hint_y  = None
            side_panel.height       = dp(148)
            side_panel.padding      = [dp(4), 0, dp(4), dp(4)]
            side_panel.spacing      = dp(2)
            if coins_leader:
                coins_leader.orientation = "horizontal"
                coins_leader.size_hint_y = 1
                coins_leader.spacing = dp(2)
            if coins_row:
                coins_row.size_hint_x = None
                coins_row.width       = dp(126)
                coins_row.size_hint_y = 1

    def _hide_name_field(self):
        field = self.ids.get("name_field")
        if field:
            field.size_hint_y = None
            field.height = 0
            field.opacity = 0

    def _post_init(self, dt):
        self._apply_orientation(Window.width, Window.height)
        self.update_board_from_state()
        self._refresh_leaderboard()
        # Delay the first AI move so the UI is fully rendered
        Clock.schedule_once(lambda dt: handle_computer_turn(self), 3)
        # Poll Firebase for leaderboard updates every 15 seconds
        Clock.schedule_interval(lambda dt: self._refresh_leaderboard(), 15)

    def _refresh_leaderboard(self, _retry=8):
        label = self.ids.get("leaderboard_label")
        if not label:
            if _retry > 0:
                Clock.schedule_once(
                    lambda dt: self._refresh_leaderboard(_retry=_retry - 1), 0.2
                )
            return
        state = self.ids.game_state

        def _on_players(players):
            # Called on the main thread once Firebase fetch completes
            lbl = self.ids.get("leaderboard_label")
            if not lbl:
                return
            lines = ["  Player            Pts"]
            for i, p in enumerate(players[:8], 1):
                lines.append(f"{i:>2}. {p['name'][:12]:<12}  {p['score']}")
            lbl.text = "\n".join(lines)

        get_online_players_async(exclude_name=state.p2_name, callback=_on_players)

    def update_board_from_state(self):
        state: GameState = self.ids.game_state
        for r in range(ROWS):
            for c in range(COLS):
                cell = self.ids.get(f"cell_{r}_{c}")
                if not cell:
                    continue
                v = state.board[r][c]
                is_last = (r == state.last_move[0] and c == state.last_move[1])
                is_win  = (r, c) in state.winning_cells
                if v == 0:
                    display_color = EMPTY_COLOR
                elif v == 1:
                    display_color = P1_COLOR if (is_win or not is_last) else LAST_P1_COLOR
                else:
                    display_color = P2_COLOR if (is_win or not is_last) else LAST_P2_COLOR

                cell.md_bg_color = display_color
                cell.is_winning = is_win
                cell.is_last_move = is_last

                # store which player is in this cell (0 = empty)
                cell.player = v

    def _handle_completed_game(self, won: bool, draw: bool):
        if won or draw:
            show_interstitial_after_game(1.0)

    def on_coin_drop(self, player: int, x: float, y: float, coin_widget):
        state: GameState = self.ids.game_state

        # Wrong player or game already over -> reset coin
        if player != state.current_player or state.game_over:
            coin_widget.pos = coin_widget.start_pos
            return

        main_grid = self.ids.get("main_grid")
        if not main_grid:
            coin_widget.pos = coin_widget.start_pos
            return

        # Restrict drop to the top row:
        # use the y-range of the row-0 cells as the allowed band.
        top_row_cell = self.ids.get("cell_0_0")
        if not top_row_cell:
            coin_widget.pos = coin_widget.start_pos
            return

        band_bottom = top_row_cell.y
        band_top = top_row_cell.top

        if y < band_bottom or y > band_top:
            coin_widget.pos = coin_widget.start_pos
            return

        # X must still be within the board horizontally
        grid_x = main_grid.x
        grid_width = main_grid.width
        if x < grid_x or x > grid_x + grid_width:
            coin_widget.pos = coin_widget.start_pos
            return

        # Compute column from x-position
        rel_x = x - grid_x
        col_width = grid_width / COLS
        col = int(rel_x // col_width)
        if col < 0 or col >= COLS:
            coin_widget.pos = coin_widget.start_pos
            return

        success, row, used_col, won, draw = state.play_move(col)
        if not success:
            coin_widget.pos = coin_widget.start_pos
            return

        self.update_board_from_state()
        coin_widget.pos = coin_widget.start_pos
        self._handle_completed_game(won, draw)

        # After the human move, let the AI respond after a 3-second pause
        if not state.game_over:
            Clock.schedule_once(lambda dt: handle_computer_turn(self), 3)

    def play_again(self):
        """Called from the 'Play Again' button."""
        state: GameState = self.ids.game_state
        state.reset_game()
        self.update_board_from_state()
        self._refresh_leaderboard()
        Clock.schedule_once(lambda dt: handle_computer_turn(self), 3)


class FiveRApp(MDApp):
    def build(self):
        # Register Python-defined widget classes so iOS frozen Kivy can find them
        Factory.register('BoardCell', cls=BoardCell)
        Factory.register('GameScreen', cls=GameScreen)
        Factory.register('GameState', cls=GameState)
        Factory.register('DraggableCoin', cls=DraggableCoin)
        self.title = "5R"
        Window.clearcolor = (0.8, 0.8, 0.8, 1)
        kv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "5r.kv")
        return Builder.load_file(kv_path)
    
    def on_start(self):
        Window.clearcolor = (0.8, 0.8, 0.8, 1)
        initialize_admob()
        store = JsonStore(os.path.join(self.user_data_dir, "profile.json"))
        if store.exists("player"):
            saved_name = store.get("player")["name"]
            self.root.ids.game_state.p2_name = saved_name
            Clock.schedule_once(lambda dt: self.root._hide_name_field(), 0.5)
        else:
            Clock.schedule_once(lambda dt: self.show_name_dialog(), 0.7)
        # Always refresh leaderboard — _post_init may have run before ids were ready
        self.root._refresh_leaderboard()

    def show_name_dialog(self):
        """Show the first-launch name picker dialog."""
        content = NamePickerContent()

        def on_save(_btn):
            name = content.name_field.text.strip()
            if not name:
                content.info_label.text = "Name cannot be empty."
                return
            if is_name_taken(name):
                suggestion = suggest_name(name)
                content.info_label.text = f"Taken!  Suggested: {suggestion}"
                content.name_field.text = suggestion
                return
            register_player(name)
            self._save_player_name(name)
            self._name_dialog.dismiss()

        self._name_dialog = MDDialog(
            title="Choose Your Display Name",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(
                    text="SKIP",
                    on_release=lambda x: self._name_dialog.dismiss(),
                ),
                MDRaisedButton(text="SAVE", on_release=on_save),
            ],
        )
        self._name_dialog.open()

    def _save_player_name(self, name: str):
        store = JsonStore(os.path.join(self.user_data_dir, "profile.json"))
        store.put("player", name=name)
        self.root.ids.game_state.p2_name = name
        self.root._hide_name_field()
        self.root._refresh_leaderboard()


if __name__ == "__main__":
    FiveRApp().run()
