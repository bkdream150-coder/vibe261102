"""
횡스크롤 플랫포머 "새싹 모험" (pygame)

머리에 새싹이 난 작은 모험가 '리프'가 되어 슬라임과 딱정벌레를 피하고,
보석을 모으며 스테이지 끝에 있는 '빛의 등대'까지 달려가는 오리지널 플랫포머.

조작법
  - ← → / A D          : 이동
  - SHIFT 또는 X       : 달리기 (누르고 있는 동안)
  - SPACE / Z / ↑ / W  : 점프 (길게 누를수록 높이 뜀)
  - P                  : 일시정지
  - M                  : 소리 켜기/끄기
  - R 또는 ENTER        : 게임 오버 후 재시작
  - ESC                : 종료

규칙
  - 적을 위에서 밟으면 쓰러뜨림 (가시고슴도치는 밟을 수 없음)
  - 연속으로 밟을수록 점수가 커짐
  - 보라색 룬 블록을 아래에서 치면 보석이나 보호막 구슬이 나오고, 나무 상자는 부서짐
  - 보호막은 한 번의 피격을 막아 줌, 보석 100개를 모으면 목숨 +1
  - 구덩이에 빠지거나 시간이 다 되면 목숨 -1, 중간 랜턴을 켜면 그곳에서 다시 시작
"""

import math
import random
import sys
from array import array

import pygame

# ---------------------------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 800, 480
FPS = 60
TILE = 40
ROWS = HEIGHT // TILE        # 12
GROUND_TOP = ROWS - 2        # 지면이 시작되는 행

GRAVITY = 0.8                # 기본 중력
GRAVITY_HOLD = 0.42          # 점프 키를 누른 채 상승할 때의 중력 (가변 점프)
JUMP_SPEED = 10.8
WALK_SPEED = 3.4
RUN_SPEED = 5.6
MAX_FALL = 13
LEVEL_TIME = 300             # 스테이지 제한 시간 (초)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (230, 60, 60)
ORANGE = (255, 150, 40)
YELLOW = (255, 230, 80)
CYAN = (80, 220, 255)
GREEN = (80, 200, 100)
GRAY = (130, 130, 140)
DARK_GRAY = (70, 70, 80)

HERO_COLOR = (70, 190, 160)
HERO_BELLY = (200, 240, 215)
LEAF_COLOR = (90, 200, 70)
SCARF_COLOR = (240, 120, 50)
GEM_COLOR = (90, 230, 255)
RUNE_COLOR = (130, 80, 200)

SOLID = set("#=CRHU")        # 지면, 돌, 나무 상자, 룬(보석), 룬(보호막), 사용된 블록
STOMP_POINTS = [100, 200, 400, 800, 1000, 2000, 4000]


def get_font(size):
    """한글 표시가 가능한 폰트를 우선 시도한다."""
    for name in ("malgungothic", "applegothic", "nanumgothic", "notosanscjkkr"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


# ---------------------------------------------------------------------------
# 효과음 (외부 파일 없이 파형을 직접 합성)
# ---------------------------------------------------------------------------
SAMPLE_RATE = 22050


class Sounds:
    def __init__(self):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        info = pygame.mixer.get_init()
        if not info or info[1] != -16:     # 16비트 오디오가 아니면 소리 끔
            return
        self.rate, _, self.channels = info
        pygame.mixer.set_num_channels(16)
        self.enabled = True

        self.sounds = {
            "jump": self._make(0.14, self._sweep(320, 760, square=True), 0.10),
            "stomp": self._make(0.12, self._sweep(700, 180, square=True), 0.16),
            "gem": self._make(0.14, self._arpeggio([1175, 1568]), 0.14),
            "bump": self._make(0.08, self._sweep(220, 110, square=True), 0.16),
            "break": self._make(0.25, self._noise(0.35), 0.40),
            "sprout": self._make(0.30, self._sweep(300, 900), 0.20),
            "powerup": self._make(0.35, self._arpeggio([523, 659, 784, 1047]), 0.20),
            "hurt": self._make(0.30, self._sweep(700, 200, square=True), 0.16),
            "oneup": self._make(0.40, self._arpeggio([660, 880, 1320, 1760]), 0.18),
            "checkpoint": self._make(0.30, self._arpeggio([784, 988, 1175]), 0.18),
            "tick": self._make(0.03, self._sweep(1500, 1500, square=True), 0.05),
            "die": self._make(0.9, self._arpeggio([523, 440, 349, 262], decay=False), 0.22),
            "clear": self._make(1.2, self._arpeggio([523, 659, 784, 1047, 1319, 1568],
                                                    decay=False), 0.20),
            "gameover": self._make(1.3, self._arpeggio([392, 330, 262, 196], decay=False), 0.26),
        }

    def _make(self, duration, gen, volume):
        n = int(self.rate * duration)
        buf = array("h")
        for i in range(n):
            k = i / n
            v = gen(i / self.rate, k) * (1 - k)      # 끝으로 갈수록 작아지는 엔벨로프
            s = int(max(-1.0, min(1.0, v)) * volume * 32767)
            buf.extend([s] * self.channels)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _sweep(self, f0, f1, square=False):
        """주파수가 f0 -> f1 로 변하는 톤 (점프, 밟기, 부딪힘)."""
        state = {"phase": 0.0}
        rate = self.rate

        def gen(t, k):
            f = f0 + (f1 - f0) * k
            state["phase"] += 2 * math.pi * f / rate
            v = math.sin(state["phase"])
            return (1.0 if v >= 0 else -1.0) if square else v
        return gen

    @staticmethod
    def _noise(smooth):
        """저역 통과 필터를 거친 노이즈 (상자 부서지는 소리)."""
        state = {"v": 0.0}

        def gen(t, k):
            state["v"] += (random.uniform(-1, 1) - state["v"]) * smooth
            return state["v"] * 3
        return gen

    @staticmethod
    def _arpeggio(freqs, decay=True):
        """음을 차례로 연주 (보석, 아이템, 클리어, 게임 오버)."""
        def gen(t, k):
            idx = min(len(freqs) - 1, int(k * len(freqs)))
            v = 1.0 if math.sin(2 * math.pi * freqs[idx] * t) >= 0 else -1.0
            if not decay:
                v *= min(3.0, 1 / (1 - k + 1e-3) ** 0.5)   # 엔벨로프를 약하게 상쇄해 길게 울림
            return v
        return gen

    def play(self, name):
        if self.enabled and not self.muted:
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted and self.enabled:
            pygame.mixer.stop()


# ---------------------------------------------------------------------------
# 스테이지 생성 (스테이지 번호를 시드로 하는 절차적 구성)
# ---------------------------------------------------------------------------
def build_level(num):
    """타일 격자, 적 배치, 중간 지점 열, 골 열을 만든다.

    타일 문자: '#' 지면, '=' 돌, 'C' 나무 상자, 'R' 룬(보석), 'H' 룬(보호막), 'o' 보석
    """
    rnd = random.Random(1000 + num * 37)
    max_w = 400
    grid = [[" "] * max_w for _ in range(ROWS)]
    spawns = []

    def put(c, r, ch):
        if 0 <= c < max_w and 0 <= r < ROWS:
            grid[r][c] = ch

    def ground(c0, c1):
        for c in range(c0, c1):
            for r in range(GROUND_TOP, ROWS):
                put(c, r, "#")

    def gems(c0, n, r):
        for i in range(n):
            put(c0 + i, r, "o")

    def pick_enemy():
        kinds = ["slime"] * 5 + ["beetle"] * (2 + num) + ["spiker"] * (1 + num // 2)
        return rnd.choice(kinds)

    def enemy(kind, c, r=GROUND_TOP - 1):
        spawns.append((kind, c, r))

    length = 170 + 20 * min(num, 4)
    max_gap = 3 if num < 3 else 4
    ground(0, 16)
    gems(8, 3, 7)
    x = 16
    checkpoint = None
    while x < length:
        if checkpoint is None and x >= length // 2:
            ground(x, x + 6)
            checkpoint = x + 3
            x += 6
            continue
        kind = rnd.choice(["flat", "pit", "blocks", "floating", "stairs", "pillars"])
        if kind == "flat":
            n = rnd.randint(7, 11)
            ground(x, x + n)
            gems(x + 2, 3, rnd.choice([6, 7]))
            enemy(pick_enemy(), x + n - 2)
            if num >= 2 and rnd.random() < 0.5:
                enemy("slime", x + n - 4)
            x += n
        elif kind == "pit":
            gap = rnd.randint(2, max_gap)
            for i in range(gap):
                put(x + i, 6 if 0 < i < gap - 1 or gap == 2 else 7, "o")
            land = rnd.randint(4, 7)
            ground(x + gap, x + gap + land)
            if rnd.random() < 0.4:
                enemy(pick_enemy(), x + gap + land - 1)
            x += gap + land
        elif kind == "blocks":
            n = 12
            ground(x, x + n)
            pattern = rnd.choice(["CRC", "CHCRC", "RCR", "CCRCC", "R C R", "CRHRC", "RRR"])
            for i, ch in enumerate(pattern):
                if ch != " ":
                    put(x + 3 + i, 7, ch)
            if rnd.random() < 0.5:
                gems(x + 4, 3, 3)
            enemy(pick_enemy(), x + n - 2)
            x += n
        elif kind == "floating":
            ground(x, x + 2)
            gap = rnd.randint(5, 7)
            pc = x + 2 + (gap - 3) // 2
            for i in range(3):
                put(pc + i, 7, "=")
            gems(pc, 3, 5)
            if num >= 1 and rnd.random() < 0.6:
                enemy("bat", pc + 1, 4)
            ground(x + 2 + gap, x + 6 + gap)
            x += 6 + gap
        elif kind == "stairs":
            h = rnd.randint(3, 4)
            ground(x, x + 2 * h + 3)
            for i in range(h):
                for j in range(i + 1):
                    put(x + i, GROUND_TOP - 1 - j, "=")
                    put(x + 2 * h - 1 - i, GROUND_TOP - 1 - j, "=")
            gems(x + h - 1, 2, GROUND_TOP - h - 2)
            x += 2 * h + 3
        else:  # pillars
            n = 12
            ground(x, x + n)
            for j in range(2):
                put(x + 3, GROUND_TOP - 1 - j, "=")
            for j in range(3):
                put(x + 8, GROUND_TOP - 1 - j, "=")
            put(x + 3, GROUND_TOP - 4, "o")
            put(x + 8, GROUND_TOP - 5, "o")
            enemy("spiker" if num >= 2 else "slime", x + 6)
            x += n

    # 마지막: 계단을 올라 등대까지
    ground(x, x + 24)
    sx = x + 3
    for i in range(5):
        for j in range(i + 1):
            put(sx + i, GROUND_TOP - 1 - j, "=")
    goal_col = sx + 10
    cols = goal_col + 10
    grid = [row[:cols] for row in grid]
    return grid, spawns, checkpoint, goal_col


class Level:
    def __init__(self, num):
        self.num = num
        self.grid, self.spawns, self.checkpoint_col, self.goal_col = build_level(num)
        self.cols = len(self.grid[0])
        self.pixel_width = self.cols * TILE
        self.bumps = {}                      # (c, r) -> 남은 튀어오름 프레임

    def get(self, c, r):
        if 0 <= c < self.cols and 0 <= r < ROWS:
            return self.grid[r][c]
        return " "

    def set(self, c, r, ch):
        if 0 <= c < self.cols and 0 <= r < ROWS:
            self.grid[r][c] = ch

    def solid(self, c, r):
        if c < 0 or c >= self.cols:         # 스테이지 양 끝은 벽
            return True
        if r < 0 or r >= ROWS:
            return False
        return self.grid[r][c] in SOLID

    @staticmethod
    def tile_range(rect):
        return (range(rect.left // TILE, (rect.right - 1) // TILE + 1),
                range(rect.top // TILE, (rect.bottom - 1) // TILE + 1))

    def solid_tiles_in(self, rect):
        cs, rs = self.tile_range(rect)
        return [(c, r) for c in cs for r in rs if self.solid(c, r)]

    def update(self):
        for key in list(self.bumps):
            self.bumps[key] -= 1
            if self.bumps[key] <= 0:
                del self.bumps[key]

    def bump_offset(self, c, r):
        t = self.bumps.get((c, r))
        if not t:
            return 0
        return -int(math.sin(math.pi * t / 10) * 8)


# ---------------------------------------------------------------------------
# 물리 바디 (타일과 축별 충돌 처리)
# ---------------------------------------------------------------------------
class Body:
    def __init__(self, x, y, w, h):
        self.x, self.y = float(x), float(y)
        self.w, self.h = w, h
        self.vx = self.vy = 0.0

    @property
    def rect(self):
        return pygame.Rect(math.floor(self.x), math.floor(self.y), self.w, self.h)

    def move_x(self, level):
        self.x += self.vx
        tiles = level.solid_tiles_in(self.rect)
        if not tiles:
            return False
        if self.vx > 0:
            self.x = min(c for c, _ in tiles) * TILE - self.w
        elif self.vx < 0:
            self.x = (max(c for c, _ in tiles) + 1) * TILE
        return True

    def move_y(self, level):
        """(착지 여부, 머리로 친 타일 목록)을 돌려준다."""
        self.y += self.vy
        tiles = level.solid_tiles_in(self.rect)
        if not tiles:
            return False, []
        landed, head = False, []
        if self.vy > 0:
            self.y = min(r for _, r in tiles) * TILE - self.h
            landed = True
        elif self.vy < 0:
            top = max(r for _, r in tiles)
            self.y = (top + 1) * TILE
            head = [(c, r) for c, r in tiles if r == top]
        self.vy = 0.0
        return landed, head


class Player(Body):
    def __init__(self, x, y):
        super().__init__(x, y, 26, 34)
        self.facing = 1
        self.on_ground = False
        self.coyote = 0              # 발판에서 떨어진 직후에도 잠깐 점프 허용
        self.jump_buffer = 0         # 착지 직전에 누른 점프 기억
        self.shield = False
        self.invuln = 0
        self.anim = 0.0
        self.combo = 0
        self.prev_bottom = y + self.h

    def update(self, level, ctl, sfx):
        self.prev_bottom = self.y + self.h
        max_speed = RUN_SPEED if ctl["run"] else WALK_SPEED
        acc = 0.35 if self.on_ground else 0.25
        if ctl["left"] and not ctl["right"]:
            self.vx -= acc
            self.facing = -1
        elif ctl["right"] and not ctl["left"]:
            self.vx += acc
            self.facing = 1
        else:
            self.vx *= 0.78 if self.on_ground else 0.96
            if abs(self.vx) < 0.1:
                self.vx = 0.0
        if abs(self.vx) > max_speed:       # 달리기를 멈추면 서서히 감속
            self.vx = math.copysign(max(max_speed, abs(self.vx) - 0.3), self.vx)

        if ctl["jump_pressed"]:
            self.jump_buffer = 6
        if self.jump_buffer > 0 and self.coyote > 0:
            self.vy = -(JUMP_SPEED + abs(self.vx) * 0.25)
            self.jump_buffer = self.coyote = 0
            self.on_ground = False
            sfx.play("jump")
        self.jump_buffer = max(0, self.jump_buffer - 1)

        g = GRAVITY_HOLD if (ctl["jump_held"] and self.vy < 0) else GRAVITY
        self.vy = min(self.vy + g, MAX_FALL)

        if self.move_x(level):
            self.vx = 0.0
        landed, head = self.move_y(level)
        self.on_ground = landed
        if landed:
            self.coyote = 6
            self.combo = 0
        else:
            self.coyote = max(0, self.coyote - 1)

        self.anim += abs(self.vx) * 0.12 if self.on_ground else 0.1
        if self.invuln > 0:
            self.invuln -= 1
        return head

    def draw(self, surf, cam, dead=False):
        if self.invuln and (self.invuln // 4) % 2 and not dead:
            return
        x, y = math.floor(self.x) - cam, math.floor(self.y)
        f = self.facing
        cx = x + 13
        moving = abs(self.vx) > 0.3 and self.on_ground

        # 발
        step = math.sin(self.anim * 3) * 4 if moving else 0
        if not self.on_ground and not dead:
            step = 3
        pygame.draw.ellipse(surf, (40, 90, 80), (cx - 11 + step, y + 27, 11, 7))
        pygame.draw.ellipse(surf, (40, 90, 80), (cx + 1 - step, y + 27, 11, 7))
        # 목도리 꼬리 (진행 방향 뒤로 펄럭임)
        flap = math.sin(self.anim * 2 + pygame.time.get_ticks() * 0.01) * 3
        pygame.draw.polygon(surf, SCARF_COLOR, [
            (cx - f * 6, y + 18), (cx - f * 20, y + 15 + flap), (cx - f * 18, y + 22 + flap),
            (cx - f * 6, y + 23)])
        # 몸통
        pygame.draw.ellipse(surf, HERO_COLOR, (x + 1, y + 7, 24, 24))
        pygame.draw.ellipse(surf, HERO_BELLY, (cx - 6 + f * 2, y + 16, 12, 13))
        pygame.draw.rect(surf, SCARF_COLOR, (x + 3, y + 18, 20, 4), border_radius=2)
        # 눈
        if dead:
            ex = cx + f * 5
            pygame.draw.line(surf, BLACK, (ex - 3, y + 11), (ex + 3, y + 17), 2)
            pygame.draw.line(surf, BLACK, (ex + 3, y + 11), (ex - 3, y + 17), 2)
        else:
            pygame.draw.circle(surf, WHITE, (cx + f * 5, y + 14), 5)
            pygame.draw.circle(surf, BLACK, (cx + f * 7, y + 14), 2)
        # 머리 위 새싹
        sway = math.sin(pygame.time.get_ticks() * 0.006) * 2
        pygame.draw.line(surf, (60, 140, 50), (cx, y + 8), (cx + sway, y + 1), 2)
        pygame.draw.ellipse(surf, LEAF_COLOR, (cx + sway - 10, y - 3, 10, 6))
        pygame.draw.ellipse(surf, LEAF_COLOR, (cx + sway, y - 4, 10, 6))

        if self.shield and not dead:
            r = 26 + int(math.sin(pygame.time.get_ticks() * 0.01) * 2)
            aura = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(aura, (120, 230, 255, 60), (r + 2, r + 2), r)
            pygame.draw.circle(aura, (160, 240, 255, 160), (r + 2, r + 2), r, 2)
            surf.blit(aura, (cx - r - 2, y + 17 - r - 2))


# ---------------------------------------------------------------------------
# 적
# ---------------------------------------------------------------------------
ENEMY_INFO = {
    # 종류: (폭, 높이, 속도)
    "slime": (30, 24, 1.0),
    "beetle": (32, 24, 1.6),
    "spiker": (30, 26, 0.8),
    "bat": (28, 20, 1.3),
}


class Enemy(Body):
    def __init__(self, kind, col, row, speed_mul):
        w, h, speed = ENEMY_INFO[kind]
        super().__init__(col * TILE + (TILE - w) // 2, (row + 1) * TILE - h, w, h)
        self.kind = kind
        self.vx = -speed * speed_mul
        self.state = "walk"          # walk / squash / flip
        self.timer = 0
        self.active = False
        self.dead = False
        self.on_ground = False
        self.anim = random.uniform(0, 6)
        self.base_y = self.y

    @property
    def alive(self):
        return self.state == "walk" and not self.dead

    def update(self, level):
        if self.state == "flip":
            self.vy += 0.6
            self.x += self.vx
            self.y += self.vy
            if self.y > HEIGHT + 100:
                self.dead = True
            return
        if self.state == "squash":
            self.timer -= 1
            if self.timer <= 0:
                self.dead = True
            return
        self.anim += 0.1
        if self.kind == "bat":
            self.x += self.vx
            self.y = self.base_y + math.sin(self.anim * 0.6) * 30
            if self.x < -100:
                self.dead = True
            return

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        if self.on_ground and self.kind in ("beetle", "spiker"):
            r = self.rect                    # 낭떠러지 앞에서 돌아섬
            fx = r.right + 1 if self.vx > 0 else r.left - 1
            if not level.solid(fx // TILE, (r.bottom + 1) // TILE):
                self.vx = -self.vx
        if self.move_x(level):
            self.vx = -self.vx
        landed, _ = self.move_y(level)
        self.on_ground = landed
        if self.y > HEIGHT + 100:
            self.dead = True

    def stomp(self):
        if self.kind == "slime":
            self.state = "squash"
            self.timer = 30
        else:
            self.flip()

    def flip(self):
        self.state = "flip"
        self.vy = -6
        self.vx = random.uniform(-1.5, 1.5)

    def draw(self, surf, cam):
        x, y = math.floor(self.x) - cam, math.floor(self.y)
        if x < -60 or x > WIDTH + 60:
            return
        w, h = self.w, self.h
        flipped = self.state == "flip"
        face = -1 if self.vx < 0 else 1
        img = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
        ox, oy = 6, 6

        if self.kind == "slime":
            if self.state == "squash":
                pygame.draw.ellipse(img, (210, 90, 190), (ox - 3, oy + h - 8, w + 6, 8))
            else:
                sq = math.sin(self.anim * 1.5) * 3
                body = (ox - sq / 2, oy + 4 + sq, w + sq, h - 4 - sq)
                pygame.draw.ellipse(img, (210, 90, 190), body)
                pygame.draw.ellipse(img, (240, 160, 230), (ox + 6, oy + 8 + sq, 8, 5))
                ex = ox + w // 2 + face * 5
                for d in (-5, 5):
                    pygame.draw.circle(img, WHITE, (ex + d, oy + 13 + sq), 4)
                    pygame.draw.circle(img, BLACK, (ex + d + face, oy + 13 + sq), 2)
        elif self.kind == "beetle":
            leg = math.sin(self.anim * 4) * 3
            for lx in (8, 16, 24):
                pygame.draw.line(img, (30, 30, 40), (ox + lx, oy + h - 6),
                                 (ox + lx + leg, oy + h), 2)
            pygame.draw.ellipse(img, (40, 70, 150), (ox, oy + 4, w, h - 6))
            pygame.draw.line(img, (20, 40, 100), (ox + w // 2, oy + 5), (ox + w // 2, oy + h - 3), 2)
            pygame.draw.ellipse(img, (120, 160, 230), (ox + 6, oy + 7, 7, 4))
            hx = ox + (w + 4 if face > 0 else -4)
            pygame.draw.circle(img, (30, 40, 70), (ox + w // 2 + face * 13, oy + 13), 6)
            pygame.draw.line(img, (200, 200, 220), (ox + w // 2 + face * 15, oy + 10), (hx, oy + 3), 3)
            pygame.draw.circle(img, YELLOW, (ox + w // 2 + face * 15, oy + 12), 2)
        elif self.kind == "spiker":
            for i in range(7):
                a = math.pi + i * math.pi / 6
                bx, by = ox + w / 2 + math.cos(a) * 11, oy + h - 10 + math.sin(a) * 11
                tx, ty = ox + w / 2 + math.cos(a) * 19, oy + h - 10 + math.sin(a) * 19
                pa = a + math.pi / 2
                pygame.draw.polygon(img, (170, 170, 180), [
                    (bx + math.cos(pa) * 4, by + math.sin(pa) * 4), (tx, ty),
                    (bx - math.cos(pa) * 4, by - math.sin(pa) * 4)])
            pygame.draw.ellipse(img, (230, 130, 50), (ox + 2, oy + 8, w - 4, h - 8))
            pygame.draw.circle(img, BLACK, (ox + w // 2 + face * 7, oy + h - 12), 2)
            pygame.draw.circle(img, (120, 50, 30), (ox + w // 2 + face * 12, oy + h - 8), 2)
        else:  # bat
            flap = math.sin(self.anim * 6) * 8
            cx, cy = ox + w // 2, oy + h // 2
            for s in (-1, 1):
                pygame.draw.polygon(img, (110, 60, 150), [
                    (cx + s * 4, cy - 2), (cx + s * 16, cy - 4 - flap),
                    (cx + s * 14, cy + 4), (cx + s * 4, cy + 4)])
            pygame.draw.circle(img, (140, 80, 180), (cx, cy), 8)
            pygame.draw.circle(img, RED, (cx - 3, cy - 1), 2)
            pygame.draw.circle(img, RED, (cx + 3, cy - 1), 2)

        if flipped:
            img = pygame.transform.flip(img, False, True)
        surf.blit(img, (x - ox, y - oy))


# ---------------------------------------------------------------------------
# 아이템 / 이펙트
# ---------------------------------------------------------------------------
class ShieldOrb(Body):
    """보호막 룬에서 솟아올라 굴러가는 구슬."""

    def __init__(self, c, r):
        super().__init__(c * TILE + 8, r * TILE, 24, 24)
        self.target_y = r * TILE - 24
        self.dead = False

    def update(self, level):
        if self.y > self.target_y:
            self.y -= 1.2
            if self.y <= self.target_y:
                self.y = self.target_y
                self.vx = 2.0
            return
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        if self.move_x(level):
            self.vx = -self.vx
        self.move_y(level)
        if self.y > HEIGHT + 50:
            self.dead = True

    def draw(self, surf, cam):
        x, y = math.floor(self.x) - cam + 12, math.floor(self.y) + 12
        t = pygame.time.get_ticks() * 0.01
        pygame.draw.circle(surf, (60, 160, 220), (x, y), 12)
        pygame.draw.circle(surf, (160, 240, 255), (x, y), 12, 2)
        pygame.draw.circle(surf, WHITE, (x - 4, y - 4), 3)
        for i in range(3):
            a = t + i * 2.1
            pygame.draw.circle(surf, (200, 250, 255), (x + math.cos(a) * 16, y + math.sin(a) * 16), 2)


class Particle:
    def __init__(self, x, y, vx, vy, color, size, life, gravity=0.4, kind="square"):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.color, self.size, self.life, self.max_life = color, size, life, life
        self.gravity = gravity
        self.kind = kind

    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy
        self.life -= 1

    def draw(self, surf, cam):
        x, y = int(self.x - cam), int(self.y)
        if self.kind == "gem":
            draw_gem(surf, x, y, 10)
        elif self.kind == "spark":
            r = max(1, int(self.size * self.life / self.max_life))
            pygame.draw.circle(surf, self.color, (x, y), r)
        else:
            pygame.draw.rect(surf, self.color, (x, y, self.size, self.size))


def draw_gem(surf, cx, cy, r, phase=0.0):
    w = max(2, int(r * 0.7 * abs(math.cos(phase)) + 2))
    pts = [(cx, cy - r), (cx + w, cy), (cx, cy + r), (cx - w, cy)]
    pygame.draw.polygon(surf, GEM_COLOR, pts)
    pygame.draw.polygon(surf, (30, 120, 170), pts, 2)
    pygame.draw.line(surf, WHITE, (cx - w // 2, cy - 2), (cx, cy - r + 3), 2)


# ---------------------------------------------------------------------------
# 게임 본체
# ---------------------------------------------------------------------------
JUMP_KEYS = (pygame.K_SPACE, pygame.K_z, pygame.K_UP, pygame.K_w)


class Game:
    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("새싹 모험")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.sfx = Sounds()
        self.font = get_font(22)
        self.small_font = get_font(16)
        self.big_font = get_font(48)
        self.high_score = 0
        self.sky = self._make_sky()
        self.reset()

    @staticmethod
    def _make_sky():
        sky = pygame.Surface((WIDTH, HEIGHT))
        top, bottom = (110, 170, 240), (200, 230, 255)
        for yy in range(HEIGHT):
            k = yy / HEIGHT
            c = [int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)]
            pygame.draw.line(sky, c, (0, yy), (WIDTH, yy))
        return sky

    def reset(self):
        self.score = 0
        self.lives = 3
        self.gems = 0
        self.level_num = 1
        self.paused = False
        self.checkpoint_reached = False
        self.start_level()

    def start_level(self):
        self.level = Level(self.level_num)
        speed_mul = 1 + 0.12 * (self.level_num - 1)
        self.enemies = [Enemy(k, c, r, speed_mul) for k, c, r in self.level.spawns
                        if not (self.checkpoint_reached and c <= self.level.checkpoint_col + 4)]
        self.items = []
        self.particles = []
        self.popups = []             # [x, y, 글자, 남은 프레임]
        col = self.level.checkpoint_col if self.checkpoint_reached else 3
        self.player = Player(col * TILE + 7, GROUND_TOP * TILE - 34)
        self.cam = 0
        self.update_camera()
        self.time_left = LEVEL_TIME * FPS
        self.state = "play"          # play / dying / clear / gameover
        self.timer = 0
        self.banner = 120

    # ----------------------------------------------------------------- 진행
    def add_score(self, pts, x=None, y=None):
        self.score += pts
        if x is not None:
            self.popups.append([x, y, str(pts), 50])

    def add_gem(self):
        self.gems += 1
        self.add_score(50)
        self.sfx.play("gem")
        if self.gems >= 100:
            self.gems -= 100
            self.lives += 1
            self.sfx.play("oneup")
            self.popups.append([self.player.x, self.player.y - 20, "1UP", 70])

    def burst(self, x, y, color, n=10, speed=4, kind="square", size=6):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(1, speed)
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s - 2,
                                           color, size, random.randint(25, 45), kind=kind))

    def bump_block(self, c, r):
        lv = self.level
        ch = lv.get(c, r)
        lv.bumps[(c, r)] = 10
        bx, by = c * TILE + TILE // 2, r * TILE
        if ch == "R":
            lv.set(c, r, "U")
            self.add_gem()
            self.particles.append(Particle(bx, by - 10, 0, -7, GEM_COLOR, 6, 28, 0.45, kind="gem"))
        elif ch == "H":
            lv.set(c, r, "U")
            self.items.append(ShieldOrb(c, r))
            self.sfx.play("sprout")
        elif ch == "C":
            lv.set(c, r, " ")
            lv.bumps.pop((c, r), None)
            self.add_score(50)
            self.sfx.play("break")
            for dx in (-1, 1):
                for dy in (-1, 1):
                    self.particles.append(Particle(bx + dx * 8, by + 20 + dy * 8, dx * 2.5,
                                                   -6 + dy * 2, (170, 110, 50), 10, 60, 0.5))
        else:
            self.sfx.play("bump")
        # 블록 위의 적과 보석도 튕겨 올림
        if lv.get(c, r - 1) == "o":
            lv.set(c, r - 1, " ")
            self.add_gem()
            self.particles.append(Particle(bx, by - 30, 0, -6, GEM_COLOR, 6, 24, 0.45, kind="gem"))
        top_zone = pygame.Rect(c * TILE, r * TILE - 6, TILE, 8)
        for e in self.enemies:
            if e.active and e.alive and e.kind != "bat" and e.rect.colliderect(top_zone):
                e.flip()
                self.add_score(200, e.x, e.y)
                self.sfx.play("stomp")

    def hurt_player(self):
        p = self.player
        if p.invuln > 0:
            return
        if p.shield:
            p.shield = False
            p.invuln = 100
            self.sfx.play("hurt")
            self.burst(p.x + 13, p.y + 17, (150, 230, 255), 14, kind="spark")
        else:
            self.kill_player()

    def kill_player(self):
        if self.state != "play":
            return
        self.state = "dying"
        self.timer = 150
        p = self.player
        p.vx = 0
        p.vy = -10
        p.shield = False
        self.sfx.play("die")

    def update_camera(self):
        target = self.player.x - WIDTH * 0.4
        self.cam = int(max(0, min(target, self.level.pixel_width - WIDTH)))

    def update(self, ctl):
        self.level.update()
        for pt in self.particles:
            pt.update()
        self.particles = [pt for pt in self.particles if pt.life > 0]
        for pp in self.popups:
            pp[1] -= 0.8
            pp[3] -= 1
        self.popups = [pp for pp in self.popups if pp[3] > 0]
        if self.banner > 0:
            self.banner -= 1

        if self.state == "play":
            self.update_play(ctl)
        elif self.state == "dying":
            p = self.player
            self.timer -= 1
            if self.timer < 120:            # 잠깐 멈췄다가 튀어오른 뒤 떨어짐
                p.vy += 0.5
                p.y += p.vy
            if self.timer <= 0:
                self.lives -= 1
                if self.lives <= 0:
                    self.state = "gameover"
                    self.high_score = max(self.high_score, self.score)
                    self.sfx.play("gameover")
                else:
                    self.start_level()
        elif self.state == "clear":
            self.timer += 1
            if self.timer > 60 and self.time_left > 0:     # 남은 시간 1초당 50점
                self.time_left -= min(self.time_left, FPS)
                self.score += 50
                if self.timer % 3 == 0:
                    self.sfx.play("tick")
                if self.time_left <= 0:
                    self.timer = 60
            elif self.timer > 60 and self.time_left <= 0 and self.timer > 180:
                self.level_num += 1
                self.checkpoint_reached = False
                self.start_level()
                return
            if self.timer % 6 == 0:
                gx = self.level.goal_col * TILE + TILE // 2
                self.particles.append(Particle(gx + random.uniform(-15, 15), 150,
                                               random.uniform(-1, 1), random.uniform(-3, -1),
                                               YELLOW, 4, 50, 0.02, kind="spark"))

    def update_play(self, ctl):
        p = self.player
        lv = self.level
        self.time_left -= 1
        if self.time_left <= 0:
            self.time_left = 0
            self.kill_player()
            return

        head = p.update(lv, ctl, self.sfx)
        if head:
            cx = p.x + p.w / 2
            c, r = min(head, key=lambda t: abs(t[0] * TILE + TILE / 2 - cx))
            self.bump_block(c, r)

        # 보석 줍기
        cs, rs = lv.tile_range(p.rect)
        for c in cs:
            for r in rs:
                if lv.get(c, r) == "o":
                    lv.set(c, r, " ")
                    self.add_gem()
                    self.burst(c * TILE + 20, r * TILE + 20, GEM_COLOR, 5, 2, kind="spark", size=3)

        # 중간 지점 / 골
        if not self.checkpoint_reached and p.x > lv.checkpoint_col * TILE:
            self.checkpoint_reached = True
            self.sfx.play("checkpoint")
            self.popups.append([p.x, p.y - 20, "CHECK!", 60])
        if p.rect.right >= lv.goal_col * TILE + 8:
            self.state = "clear"
            self.timer = 0
            p.vx = 0
            self.add_score(1000, p.x, p.y - 20)
            self.sfx.play("clear")
            return

        # 적
        activate_x = self.cam + WIDTH + 64
        for e in self.enemies:
            if not e.active and e.x < activate_x:
                e.active = True
            if e.active:
                e.update(lv)
        self.enemies = [e for e in self.enemies if not e.dead]

        pr = p.rect
        for e in self.enemies:
            if not e.alive or not pr.colliderect(e.rect):
                continue
            stomping = p.vy > 0 and p.prev_bottom <= e.rect.top + 10
            if stomping and e.kind != "spiker":
                e.stomp()
                pts = STOMP_POINTS[min(p.combo, len(STOMP_POINTS) - 1)]
                p.combo += 1
                self.add_score(pts, e.x, e.y - 10)
                p.vy = -(JUMP_SPEED if ctl["jump_held"] else 7)
                p.y = e.rect.top - p.h
                self.sfx.play("stomp")
                self.burst(e.x + e.w / 2, e.y + e.h / 2, WHITE, 6, 3, kind="spark", size=4)
            else:
                self.hurt_player()
                if self.state != "play":
                    return

        # 아이템
        for it in self.items:
            it.update(lv)
            if not it.dead and it.y <= it.target_y and pr.colliderect(it.rect):
                it.dead = True
                if p.shield:
                    self.add_score(1000, it.x, it.y)
                else:
                    p.shield = True
                self.sfx.play("powerup")
                self.burst(it.x + 12, it.y + 12, (160, 240, 255), 12, kind="spark")
        self.items = [it for it in self.items if not it.dead]

        if p.y > HEIGHT + 40:
            self.kill_player()
        self.update_camera()

    # ----------------------------------------------------------------- 그리기
    def draw_background(self):
        s = self.screen
        s.blit(self.sky, (0, 0))
        cam = self.cam
        # 구름 (가장 느리게)
        span = 300
        base = int(cam * 0.1 // span)
        off = cam * 0.1 % span
        for i in range(-1, WIDTH // span + 2):
            idx = base + i
            cx = i * span - off + (idx * 97) % 120
            cy = 50 + (idx * 37) % 90
            for dx, dy, r in ((0, 0, 22), (24, -8, 26), (50, 0, 20), (24, 6, 22)):
                pygame.draw.circle(s, (250, 250, 255), (int(cx + dx), cy + dy), r)
        # 먼 언덕 / 가까운 언덕
        for speed, span, color, rad, base_y in ((0.25, 260, (150, 205, 175), 150, HEIGHT - 40),
                                                (0.5, 190, (100, 175, 120), 90, HEIGHT - 50)):
            base = int(cam * speed // span)
            off = cam * speed % span
            for i in range(-1, WIDTH // span + 2):
                idx = base + i
                r = rad + (idx * 53) % 40
                pygame.draw.circle(s, color, (int(i * span - off + span / 2), base_y), r)

    def draw_tile(self, ch, x, y, c, r):
        s = self.screen
        t = pygame.time.get_ticks()
        if ch == "#":
            pygame.draw.rect(s, (150, 95, 55), (x, y, TILE, TILE))
            pygame.draw.circle(s, (125, 80, 45), (x + 10 + (c * 7) % 20, y + 25), 4)
            if self.level.get(c, r - 1) != "#":
                pygame.draw.rect(s, (90, 190, 70), (x, y, TILE, 10))
                for i in range(0, TILE, 8):
                    pygame.draw.polygon(s, (90, 190, 70), [(x + i, y + 10), (x + i + 4, y + 15),
                                                           (x + i + 8, y + 10)])
                pygame.draw.line(s, (140, 220, 110), (x, y), (x + TILE, y), 2)
        elif ch == "=":
            pygame.draw.rect(s, (150, 150, 165), (x, y, TILE, TILE))
            pygame.draw.rect(s, (190, 190, 205), (x, y, TILE, 5))
            pygame.draw.rect(s, (100, 100, 115), (x, y + TILE - 5, TILE, 5))
            pygame.draw.rect(s, (90, 90, 105), (x, y, TILE, TILE), 1)
        elif ch == "C":
            pygame.draw.rect(s, (190, 130, 60), (x + 1, y + 1, TILE - 2, TILE - 2))
            pygame.draw.rect(s, (120, 75, 30), (x + 1, y + 1, TILE - 2, TILE - 2), 3)
            pygame.draw.line(s, (120, 75, 30), (x + 4, y + 4), (x + TILE - 5, y + TILE - 5), 3)
            pygame.draw.line(s, (120, 75, 30), (x + TILE - 5, y + 4), (x + 4, y + TILE - 5), 3)
        elif ch in "RH":
            glow = 40 + int(math.sin(t * 0.005 + c) * 30)
            pygame.draw.rect(s, RUNE_COLOR, (x + 1, y + 1, TILE - 2, TILE - 2), border_radius=6)
            pygame.draw.rect(s, (90, 50, 150), (x + 1, y + 1, TILE - 2, TILE - 2), 3, border_radius=6)
            rc = (170 + glow, 160 + glow, 255) if ch == "R" else (120 + glow, 230, 200 + glow // 2)
            cx, cy = x + TILE // 2, y + TILE // 2
            pygame.draw.circle(s, rc, (cx, cy), 9, 2)
            pygame.draw.line(s, rc, (cx, cy - 13), (cx, cy + 13), 2)
            pygame.draw.line(s, rc, (cx - 6, cy - 7), (cx + 6, cy + 7), 2)
        elif ch == "U":
            pygame.draw.rect(s, (80, 75, 95), (x + 1, y + 1, TILE - 2, TILE - 2), border_radius=6)
            pygame.draw.rect(s, (55, 50, 70), (x + 1, y + 1, TILE - 2, TILE - 2), 3, border_radius=6)
        elif ch == "o":
            bob = math.sin(t * 0.005 + c * 0.7) * 3
            draw_gem(s, x + TILE // 2, int(y + TILE // 2 + bob), 11, t * 0.004 + c)

    def draw_level(self):
        lv = self.level
        cam = self.cam
        c0 = max(0, cam // TILE)
        c1 = min(lv.cols, (cam + WIDTH) // TILE + 2)
        for r in range(ROWS):
            row = lv.grid[r]
            for c in range(c0, c1):
                ch = row[c]
                if ch != " ":
                    self.draw_tile(ch, c * TILE - cam, r * TILE + lv.bump_offset(c, r), c, r)

        t = pygame.time.get_ticks()
        # 중간 지점 랜턴
        lx = lv.checkpoint_col * TILE + TILE // 2 - cam
        gy = GROUND_TOP * TILE
        if -40 < lx < WIDTH + 40:
            pygame.draw.rect(self.screen, (90, 60, 40), (lx - 3, gy - 90, 6, 90))
            pygame.draw.line(self.screen, (90, 60, 40), (lx, gy - 88), (lx + 18, gy - 88), 4)
            lit = self.checkpoint_reached
            color = (255, 210, 90) if lit else (110, 110, 120)
            if lit:
                glow = pygame.Surface((60, 60), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 220, 120, 70 + int(math.sin(t * 0.01) * 30)),
                                   (30, 30), 28)
                self.screen.blit(glow, (lx + 18 - 30, gy - 72 - 30))
            pygame.draw.rect(self.screen, color, (lx + 10, gy - 84, 16, 22), border_radius=4)
            pygame.draw.rect(self.screen, (60, 50, 40), (lx + 10, gy - 84, 16, 22), 2, border_radius=4)

        # 골: 빛의 등대
        gx = lv.goal_col * TILE + TILE // 2 - cam
        if -80 < gx < WIDTH + 80:
            s = self.screen
            pygame.draw.polygon(s, (200, 195, 185), [(gx - 22, gy), (gx - 12, gy - 220),
                                                     (gx + 12, gy - 220), (gx + 22, gy)])
            for i in range(1, 5):
                yy = gy - i * 45
                pygame.draw.line(s, (170, 70, 70), (gx - 20 + i * 2, yy), (gx + 20 - i * 2, yy), 6)
            pygame.draw.rect(s, (90, 80, 80), (gx - 18, gy - 236, 36, 16))
            pulse = math.sin(t * 0.006)
            if self.state == "clear":
                beam = pygame.Surface((WIDTH, 120), pygame.SRCALPHA)
                pygame.draw.polygon(beam, (255, 250, 180, 90), [(gx, 60), (0, 0), (0, 120)])
                pygame.draw.polygon(beam, (255, 250, 180, 90), [(gx, 60), (WIDTH, 0), (WIDTH, 120)])
                s.blit(beam, (0, gy - 236 - 72))
            r = 14 + int(pulse * 3)
            pts = [(gx, gy - 236 - 2 * r), (gx + r, gy - 236 - r), (gx, gy - 236), (gx - r, gy - 236 - r)]
            pygame.draw.polygon(s, (255, 240, 130) if self.state == "clear" else GEM_COLOR, pts)
            pygame.draw.polygon(s, WHITE, pts, 2)

    def draw_center_text(self, lines):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        total = sum(f.get_height() + 10 for _, f, _ in lines)
        y = HEIGHT // 2 - total // 2
        for text, font, color in lines:
            img = font.render(text, True, color)
            self.screen.blit(img, (WIDTH // 2 - img.get_width() // 2, y))
            y += img.get_height() + 10

    def draw_text_shadow(self, text, font, color, pos):
        self.screen.blit(font.render(text, True, (20, 30, 50)), (pos[0] + 2, pos[1] + 2))
        self.screen.blit(font.render(text, True, color), pos)

    def draw_hud(self):
        s = self.screen
        self.draw_text_shadow(f"점수 {self.score:07d}", self.font, WHITE, (12, 8))
        draw_gem(s, 230, 23, 10)
        self.draw_text_shadow(f"× {self.gems:02d}", self.font, WHITE, (246, 8))
        self.draw_text_shadow(f"스테이지 {self.level_num}", self.font, WHITE, (350, 8))
        secs = math.ceil(self.time_left / FPS)
        self.draw_text_shadow(f"시간 {secs:03d}", self.font, RED if secs <= 50 else WHITE, (500, 8))
        for i in range(min(self.lives, 8)):          # 목숨 = 하트
            hx, hy = 640 + i * 20, 22
            pygame.draw.circle(s, RED, (hx - 4, hy - 2), 5)
            pygame.draw.circle(s, RED, (hx + 4, hy - 2), 5)
            pygame.draw.polygon(s, RED, [(hx - 9, hy), (hx + 9, hy), (hx, hy + 9)])
        if self.lives > 8:
            self.draw_text_shadow(f"+{self.lives - 8}", self.small_font, WHITE, (700, 30))
        if self.sfx.muted:
            self.draw_text_shadow("소리 꺼짐 (M)", self.small_font, YELLOW, (WIDTH - 110, HEIGHT - 26))

    def draw(self):
        self.draw_background()
        self.draw_level()
        for it in self.items:
            it.draw(self.screen, self.cam)
        for e in self.enemies:
            if e.active:
                e.draw(self.screen, self.cam)
        if self.state != "gameover":
            self.player.draw(self.screen, self.cam, dead=self.state == "dying")
        for pt in self.particles:
            pt.draw(self.screen, self.cam)
        for x, y, text, life in self.popups:
            self.draw_text_shadow(text, self.small_font, YELLOW, (int(x - self.cam), int(y)))
        self.draw_hud()

        if self.banner > 0 and self.state == "play":
            img = self.big_font.render(f"스테이지 {self.level_num}", True, WHITE)
            self.draw_text_shadow(f"스테이지 {self.level_num}", self.big_font, WHITE,
                                  (WIDTH // 2 - img.get_width() // 2, HEIGHT // 3))
        if self.state == "clear":
            img = self.big_font.render("스테이지 클리어!", True, YELLOW)
            self.draw_text_shadow("스테이지 클리어!", self.big_font, YELLOW,
                                  (WIDTH // 2 - img.get_width() // 2, HEIGHT // 3))
        if self.state == "gameover":
            self.draw_center_text([
                ("GAME OVER", self.big_font, RED),
                (f"점수: {self.score}   최고: {self.high_score}", self.font, WHITE),
                ("R / ENTER: 다시 시작   ESC: 종료", self.font, YELLOW),
            ])
        elif self.paused:
            self.draw_center_text([("PAUSE", self.big_font, WHITE),
                                   ("P: 계속하기", self.font, YELLOW)])

    # ----------------------------------------------------------------- 루프
    def step(self, events, keys):
        """이벤트와 키 상태로 한 프레임을 진행한다 (테스트에서도 사용)."""
        jump_pressed = False
        for event in events:
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_p and self.state != "gameover":
                    self.paused = not self.paused
                if event.key == pygame.K_m:
                    self.sfx.toggle_mute()
                if event.key in (pygame.K_r, pygame.K_RETURN) and self.state == "gameover":
                    self.reset()
                if event.key in JUMP_KEYS:
                    jump_pressed = True

        ctl = {
            "left": keys[pygame.K_LEFT] or keys[pygame.K_a],
            "right": keys[pygame.K_RIGHT] or keys[pygame.K_d],
            "run": keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or keys[pygame.K_x],
            "jump_held": any(keys[k] for k in JUMP_KEYS),
            "jump_pressed": jump_pressed,
        }
        if not self.paused:
            self.update(ctl)
        self.draw()
        return True

    def run(self):
        while True:
            if not self.step(pygame.event.get(), pygame.key.get_pressed()):
                pygame.quit()
                sys.exit()
            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Game().run()
