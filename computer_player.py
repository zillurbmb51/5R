# computer_player.py
import random


def _get_valid_columns(state):
    """Return list of column indices that are not full."""
    board = state.board
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0
    valid = []
    for c in range(cols):
        if board[0][c] == 0:  # top cell empty => column not full
            valid.append(c)
    return valid


def _simulate_move(state, col, player):
    """
    Temporarily play a move in 'col' for 'player', check if it wins,
    then undo the move. Returns True if it is a winning move.
    """
    board = state.board
    rows = len(board)

    # Find lowest empty row in column
    target_row = None
    for r in range(rows - 1, -1, -1):
        if board[r][col] == 0:
            target_row = r
            break
    if target_row is None:
        return False  # column full

    # Play move
    board[target_row][col] = player
    won, _ = state.check_win(target_row, col)
    # Undo move
    board[target_row][col] = 0
    return won


def choose_best_column(state):
    """
    Simple AI for Player 1:
    1) If it can win immediately, do that.
    2) Else, if Player 2 can win next turn, block that.
    3) Else, prefer center column(s).
    4) Else, pick random valid column.
    """
    board = state.board
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0

    valid_cols = _get_valid_columns(state)
    if not valid_cols:
        return None

    my_player = 1
    opp_player = 2

    # 1. Try to win immediately
    for c in valid_cols:
        if _simulate_move(state, c, my_player):
            return c

    # 2. Block opponent's immediate win
    for c in valid_cols:
        if _simulate_move(state, c, opp_player):
            return c

    # 3. Prefer center columns
    center = cols // 2
    # sort valid cols by distance to center
    sorted_by_center = sorted(valid_cols, key=lambda c: abs(c - center))
    return sorted_by_center[0]


def handle_computer_turn(game_screen):
    """
    Called by GameScreen when it's Player 1's turn.
    Plays one move for the computer if possible.
    """
    state = game_screen.ids.game_state

    if state.game_over:
        return
    if state.current_player != 1:
        return

    col = choose_best_column(state)
    if col is None:
        return

    # Use existing game logic to play the move
    success, row, used_col, won, draw = state.play_move(col)
    if not success:
        return

    # Update the board view after the AI move
    game_screen.update_board_from_state()
    if hasattr(game_screen, "_handle_completed_game"):
        game_screen._handle_completed_game(won, draw)
