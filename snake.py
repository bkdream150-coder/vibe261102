"""뱀 게임 (tkinter 사용 - 별도 설치 불필요)

조작법:
  방향키 / WASD : 이동
  P             : 일시정지
  R             : 재시작 (게임 오버 후)
  Esc           : 종료
"""

import random
import tkinter as tk

CELL = 20          # 칸 크기(px)
COLS = 30          # 가로 칸 수
ROWS = 24          # 세로 칸 수
START_SPEED = 120  # 시작 속도(ms, 작을수록 빠름)
MIN_SPEED = 50     # 최고 속도

BG_COLOR = "#1e1e2e"
SNAKE_HEAD = "#a6e3a1"
SNAKE_BODY = "#40a02b"
FOOD_COLOR = "#f38ba8"
TEXT_COLOR = "#cdd6f4"

DIRECTIONS = {
    "Up": (0, -1), "w": (0, -1), "W": (0, -1),
    "Down": (0, 1), "s": (0, 1), "S": (0, 1),
    "Left": (-1, 0), "a": (-1, 0), "A": (-1, 0),
    "Right": (1, 0), "d": (1, 0), "D": (1, 0),
}


class SnakeGame:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("뱀 게임")
        self.root.resizable(False, False)

        self.score_label = tk.Label(
            root, font=("Consolas", 14, "bold"), bg=BG_COLOR, fg=TEXT_COLOR
        )
        self.score_label.pack(fill="x")

        self.canvas = tk.Canvas(
            root, width=COLS * CELL, height=ROWS * CELL,
            bg=BG_COLOR, highlightthickness=0,
        )
        self.canvas.pack()

        self.high_score = 0
        self.after_id = None
        root.bind("<Key>", self.on_key)
        self.reset()

    # ---------- 게임 상태 ----------
    def reset(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        cx, cy = COLS // 2, ROWS // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.speed = START_SPEED
        self.paused = False
        self.game_over = False
        self.food = self.spawn_food()
        self.update_score()
        self.tick()

    def spawn_food(self):
        occupied = set(self.snake)
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in occupied]
        return random.choice(free) if free else None

    def update_score(self):
        self.score_label.config(
            text=f"점수: {self.score}    최고 점수: {self.high_score}"
        )

    # ---------- 입력 ----------
    def on_key(self, event):
        key = event.keysym
        if key == "Escape":
            self.root.destroy()
        elif key in ("r", "R") and self.game_over:
            self.reset()
        elif key in ("p", "P") and not self.game_over:
            self.paused = not self.paused
            self.draw()
        elif key in DIRECTIONS:
            dx, dy = DIRECTIONS[key]
            # 반대 방향으로는 바로 꺾을 수 없음
            if (dx, dy) != (-self.direction[0], -self.direction[1]):
                self.next_direction = (dx, dy)

    # ---------- 게임 루프 ----------
    def tick(self):
        if not self.paused and not self.game_over:
            self.step()
        self.draw()
        if not self.game_over:
            self.after_id = self.root.after(self.speed, self.tick)

    def step(self):
        self.direction = self.next_direction
        hx, hy = self.snake[0]
        new_head = (hx + self.direction[0], hy + self.direction[1])

        # 벽 또는 자기 몸에 부딪히면 게임 오버 (꼬리는 이번에 이동하므로 제외)
        x, y = new_head
        hit_wall = not (0 <= x < COLS and 0 <= y < ROWS)
        hit_self = new_head in self.snake[:-1]
        if hit_wall or hit_self:
            self.end_game()
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 10
            self.high_score = max(self.high_score, self.score)
            self.speed = max(MIN_SPEED, self.speed - 3)
            self.update_score()
            self.food = self.spawn_food()
            if self.food is None:  # 화면을 꽉 채움 = 승리
                self.end_game(win=True)
        else:
            self.snake.pop()

    def end_game(self, win=False):
        self.game_over = True
        self.win = win

    # ---------- 그리기 ----------
    def draw(self):
        c = self.canvas
        c.delete("all")

        if self.food:
            fx, fy = self.food
            c.create_oval(
                fx * CELL + 3, fy * CELL + 3, (fx + 1) * CELL - 3, (fy + 1) * CELL - 3,
                fill=FOOD_COLOR, outline="",
            )

        for i, (x, y) in enumerate(self.snake):
            c.create_rectangle(
                x * CELL + 1, y * CELL + 1, (x + 1) * CELL - 1, (y + 1) * CELL - 1,
                fill=SNAKE_HEAD if i == 0 else SNAKE_BODY, outline="",
            )

        w, h = COLS * CELL, ROWS * CELL
        if self.game_over:
            title = "승리!" if getattr(self, "win", False) else "게임 오버"
            c.create_text(w / 2, h / 2 - 20, text=title,
                          fill=TEXT_COLOR, font=("Consolas", 28, "bold"))
            c.create_text(w / 2, h / 2 + 20, text=f"점수: {self.score}   R: 재시작   Esc: 종료",
                          fill=TEXT_COLOR, font=("Consolas", 13))
        elif self.paused:
            c.create_text(w / 2, h / 2, text="일시정지 (P)",
                          fill=TEXT_COLOR, font=("Consolas", 24, "bold"))


if __name__ == "__main__":
    root = tk.Tk()
    root.configure(bg=BG_COLOR)
    SnakeGame(root)
    root.mainloop()
