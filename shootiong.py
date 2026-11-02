"""
종스크롤 슈팅 게임 (pygame)

조작법
  - 방향키 / WASD : 이동
  - Z 또는 SPACE  : 공중 레이저 (공중 적 공격)
  - X             : 폭탄 (지상 목표 공격, 조준점 위치에 떨어짐)
  - P             : 일시정지
  - M             : 소리 켜기/끄기
  - R             : 게임 오버 후 재시작
  - ESC           : 종료
"""

import math
import random
import sys
from array import array

import pygame

# ---------------------------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 480, 720
FPS = 60
SCROLL_SPEED = 1.5          # 지면 스크롤 속도 (픽셀/프레임)
TILE = 48                   # 지형 타일 크기

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (230, 60, 60)
ORANGE = (255, 150, 40)
YELLOW = (255, 230, 80)
CYAN = (80, 220, 255)
GREEN = (80, 200, 100)
GRAY = (130, 130, 140)
DARK_GRAY = (70, 70, 80)

GRASS_COLORS = [(46, 110, 60), (52, 120, 66), (40, 100, 55)]
FOREST_COLOR = (25, 75, 40)
ROAD_COLOR = (150, 140, 110)
WATER_COLOR = (40, 90, 160)


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
            "laser": self._make(0.07, self._sweep(1400, 500, square=True), 0.12),
            "bomb": self._make(0.35, self._sweep(900, 250), 0.25),
            "hit": self._make(0.04, self._sweep(600, 300, square=True), 0.12),
            "explode": self._make(0.35, self._noise(0.3), 0.45),
            "big_explode": self._make(0.7, self._noise(0.12), 0.6),
            "ground": self._make(0.45, self._noise(0.08), 0.55),
            "powerup": self._make(0.32, self._arpeggio([523, 659, 784, 1047]), 0.25),
            "die": self._make(1.0, self._noise(0.05, falling=True), 0.7),
            "gameover": self._make(1.2, self._arpeggio([392, 330, 262, 196], decay=False), 0.3),
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

    @staticmethod
    def _sweep(f0, f1, square=False):
        """주파수가 f0 -> f1 로 변하는 톤 (레이저, 폭탄 낙하음)."""
        state = {"phase": 0.0}

        def gen(t, k):
            f = f0 + (f1 - f0) * k
            state["phase"] += 2 * math.pi * f / SAMPLE_RATE
            v = math.sin(state["phase"])
            return (1.0 if v >= 0 else -1.0) if square else v
        return gen

    @staticmethod
    def _noise(smooth, falling=False):
        """저역 통과 필터를 거친 노이즈 (폭발음). smooth 가 작을수록 묵직한 소리."""
        state = {"v": 0.0}

        def gen(t, k):
            a = smooth * (1 - k * 0.8) if falling else smooth
            state["v"] += (random.uniform(-1, 1) - state["v"]) * a
            return state["v"] * 3
        return gen

    @staticmethod
    def _arpeggio(freqs, decay=True):
        """음을 차례로 연주 (아이템 획득, 게임 오버)."""
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
# 스크롤 배경 (절차적으로 생성되는 지형)
# ---------------------------------------------------------------------------
class Background:
    def __init__(self):
        self.cols = WIDTH // TILE + 1
        self.rows = HEIGHT // TILE + 2
        self.offset = 0.0
        self.river_x = random.randint(2, self.cols - 3)
        self.road_x = random.randint(0, self.cols - 1)
        self.rows_data = [self._make_row() for _ in range(self.rows)]

    def _make_row(self):
        # 강과 도로가 구불구불 이어지도록 조금씩 이동
        self.river_x = max(1, min(self.cols - 2, self.river_x + random.choice((-1, 0, 0, 1))))
        if random.random() < 0.15:
            self.road_x = max(0, min(self.cols - 1, self.road_x + random.choice((-1, 1))))
        row = []
        for c in range(self.cols):
            if c == self.river_x:
                row.append(("water", None))
            elif c == self.road_x:
                row.append(("road", None))
            elif random.random() < 0.18:
                row.append(("forest", None))
            else:
                row.append(("grass", random.choice(GRASS_COLORS)))
        return row

    def update(self):
        self.offset += SCROLL_SPEED
        if self.offset >= TILE:
            self.offset -= TILE
            self.rows_data.pop()               # 화면 아래로 사라진 줄 제거
            self.rows_data.insert(0, self._make_row())  # 위에 새 줄 추가

    def draw(self, surf):
        for r, row in enumerate(self.rows_data):
            y = (r - 1) * TILE + self.offset
            for c, (kind, color) in enumerate(row):
                rect = pygame.Rect(c * TILE, int(y), TILE, TILE + 1)
                if kind == "water":
                    pygame.draw.rect(surf, WATER_COLOR, rect)
                elif kind == "road":
                    pygame.draw.rect(surf, ROAD_COLOR, rect)
                elif kind == "forest":
                    pygame.draw.rect(surf, GRASS_COLORS[0], rect)
                    pygame.draw.circle(surf, FOREST_COLOR, rect.center, TILE // 2 - 4)
                else:
                    pygame.draw.rect(surf, color, rect)


# ---------------------------------------------------------------------------
# 플레이어
# ---------------------------------------------------------------------------
class Player(pygame.sprite.Sprite):
    SPEED = 5

    def __init__(self):
        super().__init__()
        self.image = pygame.Surface((36, 40), pygame.SRCALPHA)
        pygame.draw.polygon(self.image, (210, 210, 230), [(18, 0), (34, 34), (18, 26), (2, 34)])
        pygame.draw.polygon(self.image, CYAN, [(18, 8), (24, 24), (12, 24)])
        pygame.draw.rect(self.image, ORANGE, (14, 32, 8, 8))
        self.rect = self.image.get_rect(center=(WIDTH // 2, HEIGHT - 80))
        self.hitbox = self.rect.inflate(-24, -24)
        self.shot_cooldown = 0
        self.bomb_cooldown = 0
        self.power = 1           # 레이저 단계 (1~3)
        self.invincible = 120    # 시작/부활 시 무적 프레임

    def update(self, keys):
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        if dx and dy:
            dx *= 0.7071
            dy *= 0.7071
        self.rect.x += round(dx * self.SPEED)
        self.rect.y += round(dy * self.SPEED)
        self.rect.clamp_ip(pygame.Rect(0, 120, WIDTH, HEIGHT - 120))
        self.hitbox.center = self.rect.center

        self.shot_cooldown = max(0, self.shot_cooldown - 1)
        self.bomb_cooldown = max(0, self.bomb_cooldown - 1)
        self.invincible = max(0, self.invincible - 1)

    @property
    def target_pos(self):
        """폭탄 조준점: 기체 앞쪽 일정 거리."""
        return self.rect.centerx, self.rect.centery - 160

    def draw(self, surf):
        # 무적 상태일 땐 깜빡임
        if self.invincible and (self.invincible // 5) % 2 == 0:
            return
        surf.blit(self.image, self.rect)


# ---------------------------------------------------------------------------
# 무기
# ---------------------------------------------------------------------------
class Laser(pygame.sprite.Sprite):
    def __init__(self, x, y, vx=0.0):
        super().__init__()
        self.image = pygame.Surface((4, 16), pygame.SRCALPHA)
        self.image.fill(YELLOW)
        self.rect = self.image.get_rect(center=(x, y))
        self.vx = vx
        self.fx = float(x)

    def update(self):
        self.rect.y -= 12
        self.fx += self.vx
        self.rect.centerx = int(self.fx)
        if self.rect.bottom < 0:
            self.kill()


class Bomb(pygame.sprite.Sprite):
    """플레이어 위치에서 조준점까지 날아가 폭발하는 지상 공격 폭탄."""

    def __init__(self, start, target):
        super().__init__()
        self.start = pygame.Vector2(start)
        self.target = pygame.Vector2(target)
        self.t = 0
        self.duration = 30
        self.image = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(self.image, ORANGE, (5, 5), 5)
        self.rect = self.image.get_rect(center=start)
        self.exploded = False

    def update(self):
        self.t += 1
        self.target.y += SCROLL_SPEED  # 조준점도 지면과 함께 내려감
        k = self.t / self.duration
        pos = self.start.lerp(self.target, k)
        size = max(4, int(10 * (1 - k * 0.6)))   # 멀어질수록 작게
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.image, ORANGE, (size // 2, size // 2), size // 2)
        self.rect = self.image.get_rect(center=pos)
        if self.t >= self.duration:
            self.exploded = True
            self.kill()


class EnemyBullet(pygame.sprite.Sprite):
    def __init__(self, pos, vel):
        super().__init__()
        self.image = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.circle(self.image, (255, 120, 200), (4, 4), 4)
        pygame.draw.circle(self.image, WHITE, (4, 4), 2)
        self.rect = self.image.get_rect(center=pos)
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)

    def update(self):
        self.pos += self.vel
        self.rect.center = self.pos
        if not pygame.Rect(-20, -20, WIDTH + 40, HEIGHT + 40).colliderect(self.rect):
            self.kill()


def aimed_bullet(src, dst, speed):
    d = pygame.Vector2(dst) - pygame.Vector2(src)
    if d.length() == 0:
        d = pygame.Vector2(0, 1)
    return EnemyBullet(src, d.normalize() * speed)


# ---------------------------------------------------------------------------
# 공중 적
# ---------------------------------------------------------------------------
class AirEnemy(pygame.sprite.Sprite):
    def __init__(self, kind, x, game):
        super().__init__()
        self.kind = kind
        self.game = game
        self.t = 0
        self.base_x = x
        if kind == "dart":          # 빠르게 내려오다 플레이어 방향으로 꺾음
            self.hp, self.score = 1, 100
            self.image = self._make_shape(RED, 26)
        elif kind == "wave":        # 사인파로 흔들리며 내려옴
            self.hp, self.score = 1, 150
            self.image = self._make_shape((200, 120, 255), 24, diamond=True)
        else:                       # "tank": 단단하고 탄을 뿌림
            self.hp, self.score = 6, 500
            self.image = self._make_shape(GRAY, 40, heavy=True)
        self.rect = self.image.get_rect(center=(x, -30))
        self.pos = pygame.Vector2(self.rect.center)
        self.vel = pygame.Vector2(0, 3 if kind == "dart" else 2)
        self.flash = 0

    @staticmethod
    def _make_shape(color, size, diamond=False, heavy=False):
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        h = size // 2
        if diamond:
            pygame.draw.polygon(s, color, [(h, 0), (size, h), (h, size), (0, h)])
            pygame.draw.circle(s, WHITE, (h, h), size // 6)
        elif heavy:
            pygame.draw.circle(s, color, (h, h), h)
            pygame.draw.circle(s, DARK_GRAY, (h, h), h - 6)
            pygame.draw.circle(s, RED, (h, h), h // 3)
        else:
            pygame.draw.polygon(s, color, [(0, 0), (size, 0), (h, size)])
            pygame.draw.circle(s, YELLOW, (h, size // 3), size // 7)
        return s

    def update(self):
        self.t += 1
        player = self.game.player
        if self.kind == "dart":
            if self.t == 40 and player.alive():
                d = pygame.Vector2(player.rect.center) - self.pos
                if d.length():
                    self.vel = d.normalize() * 5
        elif self.kind == "wave":
            self.pos.x = self.base_x + math.sin(self.t * 0.06) * 80
            if self.t % 70 == 35 and player.alive():
                self.game.enemy_bullets.add(aimed_bullet(self.pos, player.rect.center, 4))
        else:
            if self.pos.y > 140:
                self.vel.y = 0.4
            if self.t % 50 == 0:
                for i in range(8):     # 원형 탄막
                    ang = math.radians(i * 45 + self.t)
                    self.game.enemy_bullets.add(
                        EnemyBullet(self.pos, (math.cos(ang) * 3, math.sin(ang) * 3)))
        self.pos += self.vel
        self.rect.center = self.pos
        self.flash = max(0, self.flash - 1)
        if self.rect.top > HEIGHT + 40 or self.rect.right < -60 or self.rect.left > WIDTH + 60:
            self.kill()

    def hit(self, dmg=1):
        self.hp -= dmg
        self.flash = 4
        return self.hp <= 0

    def draw(self, surf):
        if self.flash:
            white = self.image.copy()
            white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
            surf.blit(white, self.rect)
        else:
            surf.blit(self.image, self.rect)


# ---------------------------------------------------------------------------
# 지상 적 (폭탄으로만 파괴 가능, 지면과 함께 스크롤)
# ---------------------------------------------------------------------------
class GroundEnemy(pygame.sprite.Sprite):
    def __init__(self, x, game, kind="turret"):
        super().__init__()
        self.game = game
        self.kind = kind
        self.image = pygame.Surface((36, 36), pygame.SRCALPHA)
        if kind == "turret":
            pygame.draw.rect(self.image, DARK_GRAY, (2, 2, 32, 32), border_radius=6)
            pygame.draw.circle(self.image, GRAY, (18, 18), 11)
            pygame.draw.circle(self.image, RED, (18, 18), 5)
            self.score = 300
        else:   # "depot": 파괴 시 파워업 아이템
            pygame.draw.rect(self.image, (160, 120, 60), (2, 2, 32, 32))
            pygame.draw.line(self.image, (90, 60, 30), (2, 2), (34, 34), 3)
            pygame.draw.line(self.image, (90, 60, 30), (34, 2), (2, 34), 3)
            self.score = 200
        self.rect = self.image.get_rect(center=(x, -20))
        self.fy = float(self.rect.centery)
        self.t = random.randint(0, 60)

    def update(self):
        self.fy += SCROLL_SPEED
        self.rect.centery = int(self.fy)
        self.t += 1
        player = self.game.player
        if (self.kind == "turret" and self.t % 90 == 0 and 0 < self.rect.centery < HEIGHT - 150
                and player.alive()):
            self.game.enemy_bullets.add(aimed_bullet(self.rect.center, player.rect.center, 3.5))
        if self.rect.top > HEIGHT:
            self.kill()


# ---------------------------------------------------------------------------
# 이펙트 / 아이템
# ---------------------------------------------------------------------------
class Explosion(pygame.sprite.Sprite):
    def __init__(self, pos, size=30):
        super().__init__()
        self.pos = pos
        self.max_r = size
        self.t = 0
        self.life = 20
        self.image = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=pos)

    def update(self):
        self.t += 1
        k = self.t / self.life
        self.image.fill((0, 0, 0, 0))
        r = int(self.max_r * k)
        alpha = int(255 * (1 - k))
        pygame.draw.circle(self.image, (255, 200, 80, alpha), (self.max_r, self.max_r), max(r, 1))
        pygame.draw.circle(self.image, (255, 255, 255, alpha), (self.max_r, self.max_r), max(r // 2, 1))
        if self.t >= self.life:
            self.kill()


class PowerUp(pygame.sprite.Sprite):
    def __init__(self, pos):
        super().__init__()
        self.image = pygame.Surface((22, 22), pygame.SRCALPHA)
        pygame.draw.circle(self.image, GREEN, (11, 11), 11)
        pygame.draw.polygon(self.image, WHITE, [(11, 4), (17, 14), (5, 14)])
        self.rect = self.image.get_rect(center=pos)
        self.fy = float(pos[1])

    def update(self):
        self.fy += SCROLL_SPEED + 0.5
        self.rect.centery = int(self.fy)
        if self.rect.top > HEIGHT:
            self.kill()


# ---------------------------------------------------------------------------
# 게임 본체
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("종스크롤 슈팅")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.sfx = Sounds()
        self.font = get_font(22)
        self.big_font = get_font(48)
        self.high_score = 0
        self.reset()

    def reset(self):
        self.bg = Background()
        self.player = Player()
        self.players = pygame.sprite.GroupSingle(self.player)
        self.lasers = pygame.sprite.Group()
        self.bombs = pygame.sprite.Group()
        self.air_enemies = pygame.sprite.Group()
        self.ground_enemies = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.effects = pygame.sprite.Group()
        self.powerups = pygame.sprite.Group()
        self.score = 0
        self.lives = 3
        self.frame = 0
        self.game_over = False
        self.paused = False
        self.respawn_timer = 0

    # ---- 적 생성 ----------------------------------------------------------
    def spawn(self):
        level = 1 + self.frame // 1800          # 30초마다 난이도 상승
        f = self.frame

        if f % max(20, 70 - level * 8) == 0:
            if random.random() < 0.5:
                # 편대 비행
                x = random.randint(60, WIDTH - 60)
                for i in range(3):
                    e = AirEnemy("dart", x + (i - 1) * 40, self)
                    e.pos.y -= i * 30
                    self.air_enemies.add(e)
            else:
                self.air_enemies.add(AirEnemy("wave", random.randint(100, WIDTH - 100), self))

        if f % max(400, 900 - level * 100) == 0 and f > 0:
            self.air_enemies.add(AirEnemy("tank", random.randint(80, WIDTH - 80), self))

        if f % 110 == 0:
            kind = "depot" if random.random() < 0.2 else "turret"
            self.ground_enemies.add(GroundEnemy(random.randint(30, WIDTH - 30), self, kind))

    # ---- 입력 -------------------------------------------------------------
    def handle_fire(self, keys):
        p = self.player
        if not p.alive():
            return
        if (keys[pygame.K_z] or keys[pygame.K_SPACE]) and p.shot_cooldown == 0:
            x, y = p.rect.centerx, p.rect.top
            if p.power == 1:
                self.lasers.add(Laser(x - 6, y), Laser(x + 6, y))
            elif p.power == 2:
                self.lasers.add(Laser(x - 8, y), Laser(x, y - 4), Laser(x + 8, y))
            else:
                self.lasers.add(Laser(x - 8, y), Laser(x + 8, y),
                                Laser(x - 12, y, -1.5), Laser(x + 12, y, 1.5),
                                Laser(x, y - 4))
            p.shot_cooldown = 7
            self.sfx.play("laser")
        if keys[pygame.K_x] and p.bomb_cooldown == 0 and len(self.bombs) < 2:
            self.bombs.add(Bomb(p.rect.midtop, p.target_pos))
            p.bomb_cooldown = 20
            self.sfx.play("bomb")

    # ---- 충돌 처리 --------------------------------------------------------
    def collisions(self):
        # 레이저 -> 공중 적
        hits = pygame.sprite.groupcollide(self.air_enemies, self.lasers, False, True)
        for enemy, lasers in hits.items():
            if enemy.hit(len(lasers)):
                self.score += enemy.score
                self.effects.add(Explosion(enemy.rect.center, 40 if enemy.kind == "tank" else 25))
                if enemy.kind == "tank":
                    self.powerups.add(PowerUp(enemy.rect.center))
                    self.sfx.play("big_explode")
                else:
                    self.sfx.play("explode")
                enemy.kill()
            else:
                self.sfx.play("hit")

        # 플레이어 <-> 아이템
        p = self.player
        if p.alive():
            for item in pygame.sprite.spritecollide(p, self.powerups, True):
                self.sfx.play("powerup")
                if p.power < 3:
                    p.power += 1
                else:
                    self.score += 1000

        # 피격 판정 (작은 히트박스 사용)
        if p.alive() and not p.invincible:
            hit = any(p.hitbox.colliderect(b.rect) for b in self.enemy_bullets) or \
                  any(p.hitbox.colliderect(e.rect.inflate(-6, -6)) for e in self.air_enemies)
            if hit:
                self.player_die()

    def bomb_explode(self, pos):
        self.effects.add(Explosion(pos, 28))
        blast = pygame.Rect(0, 0, 40, 40)
        blast.center = pos
        for g in list(self.ground_enemies):
            if blast.colliderect(g.rect):
                self.score += g.score
                self.effects.add(Explosion(g.rect.center, 35))
                self.sfx.play("ground")
                if g.kind == "depot":
                    self.powerups.add(PowerUp(g.rect.center))
                g.kill()

    def player_die(self):
        p = self.player
        self.effects.add(Explosion(p.rect.center, 50))
        p.kill()
        self.enemy_bullets.empty()
        self.lives -= 1
        self.sfx.play("die")
        if self.lives <= 0:
            self.game_over = True
            self.high_score = max(self.high_score, self.score)
            self.sfx.play("gameover")
        else:
            self.respawn_timer = 90

    # ---- 메인 루프 --------------------------------------------------------
    def update(self):
        keys = pygame.key.get_pressed()
        self.frame += 1
        self.bg.update()
        self.spawn()

        if self.player.alive():
            self.player.update(keys)
        elif self.respawn_timer > 0:
            self.respawn_timer -= 1
            if self.respawn_timer == 0:
                power = max(1, self.player.power - 1)
                self.player = Player()
                self.player.power = power
                self.players.add(self.player)

        self.handle_fire(keys)
        self.lasers.update()
        for b in list(self.bombs):
            b.update()
            if b.exploded:
                self.bomb_explode(b.rect.center)
        self.ground_enemies.update()
        self.air_enemies.update()
        self.enemy_bullets.update()
        self.effects.update()
        self.powerups.update()
        self.collisions()

    def draw_hud(self):
        s = self.screen
        s.blit(self.font.render(f"SCORE {self.score:07d}", True, WHITE), (10, 8))
        s.blit(self.font.render(f"HI {max(self.high_score, self.score):07d}", True, YELLOW),
               (WIDTH - 170, 8))
        for i in range(self.lives):
            pygame.draw.polygon(s, CYAN, [(18 + i * 22, 40), (28 + i * 22, 58), (8 + i * 22, 58)])
        s.blit(self.font.render(f"POWER {self.player.power}", True, GREEN), (10, 64))

    def draw_center_text(self, lines):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        y = HEIGHT // 2 - 60
        for text, font, color in lines:
            img = font.render(text, True, color)
            self.screen.blit(img, img.get_rect(center=(WIDTH // 2, y)))
            y += img.get_height() + 16

    def draw(self):
        self.bg.draw(self.screen)
        self.ground_enemies.draw(self.screen)
        self.powerups.draw(self.screen)
        for e in self.air_enemies:
            e.draw(self.screen)
        self.lasers.draw(self.screen)
        self.bombs.draw(self.screen)
        if self.player.alive():
            self.player.draw(self.screen)
            # 폭탄 조준점
            tx, ty = self.player.target_pos
            pygame.draw.circle(self.screen, RED, (tx, ty), 12, 2)
            pygame.draw.line(self.screen, RED, (tx - 16, ty), (tx + 16, ty), 1)
            pygame.draw.line(self.screen, RED, (tx, ty - 16), (tx, ty + 16), 1)
        self.enemy_bullets.draw(self.screen)
        self.effects.draw(self.screen)
        self.draw_hud()

        if self.game_over:
            self.draw_center_text([
                ("GAME OVER", self.big_font, RED),
                (f"점수: {self.score}", self.font, WHITE),
                ("R: 다시 시작   ESC: 종료", self.font, YELLOW),
            ])
        elif self.paused:
            self.draw_center_text([("PAUSE", self.big_font, WHITE),
                                   ("P: 계속하기", self.font, YELLOW)])
        pygame.display.flip()

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if event.key == pygame.K_p and not self.game_over:
                        self.paused = not self.paused
                    if event.key == pygame.K_m:
                        self.sfx.toggle_mute()
                    if event.key == pygame.K_r and self.game_over:
                        self.reset()

            if not self.game_over and not self.paused:
                self.update()
            elif self.game_over:
                # 게임 오버 중에도 배경과 이펙트는 계속 움직이게
                self.bg.update()
                self.effects.update()
            self.draw()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Game().run()
