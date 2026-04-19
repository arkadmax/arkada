"""
Простая аркада: платформа, мяч, кирпичи, бонусы с цветных кирпичей.
Зависимость: pip install pygame
Визуал: лаконичный интерфейс, линейные и радиальные градиенты.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Sequence, Tuple

import pygame

Color = Tuple[int, int, int]


# --- константы (размеры экрана и скорости; «стиль» не зафиксирован) ---

SCREEN_W = 800
SCREEN_H = 600
FPS = 60

PADDLE_Y = SCREEN_H - 40
PADDLE_SPEED = 360.0  # пикселей в секунду
PADDLE_H = 14
PADDLE_INITIAL_W = 100

BALL_RADIUS = 8
BALL_SPEED = 280.0  # модуль скорости после отскока от платформы

BRICK_ROWS = 5
BRICK_COLS = 10
BRICK_TOP = 60
BRICK_H = 24
BRICK_GAP = 4
BRICK_MARGIN_X = 40

SPECIAL_BRICK_FRACTION = 0.15  # доля «цветных» кирпичей с бонусом
POWERUP_FALL_SPEED = 120.0
PADDLE_GROWTH = 1.15  # +15%
PADDLE_MAX_W_FRACTION = 0.85  # не шире 85% экрана

# палитра (градиенты «сверху / слева» → «снизу / справа»)
UI_BG_TOP = (26, 30, 48)
UI_BG_BOTTOM = (12, 14, 24)
UI_BRICK_TOP = (72, 78, 102)
UI_BRICK_BOTTOM = (42, 46, 68)
UI_BRICK_SPECIAL_TOP = (140, 96, 118)
UI_BRICK_SPECIAL_BOTTOM = (82, 52, 72)
UI_PADDLE_LEFT = (218, 222, 240)
UI_PADDLE_RIGHT = (148, 154, 182)
UI_BALL_CORE = (255, 236, 178)
UI_BALL_EDGE = (190, 120, 64)
UI_POWER_CORE = (200, 248, 255)
UI_POWER_EDGE = (52, 140, 198)
UI_TEXT_DIM = (200, 204, 220)
UI_TEXT_ACCENT = (255, 255, 255)


def _lerp_byte(a: int, b: int, t: float) -> int:
    return int(max(0, min(255, round(a + (b - a) * t))))


def lerp_color(c0: Color, c1: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        _lerp_byte(c0[0], c1[0], t),
        _lerp_byte(c0[1], c1[1], t),
        _lerp_byte(c0[2], c1[2], t),
    )


def make_vertical_gradient(size: Tuple[int, int], top: Color, bottom: Color) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size)
    if h <= 1:
        surf.fill(top)
        return surf
    for y in range(h):
        t = y / (h - 1)
        pygame.draw.line(surf, lerp_color(top, bottom, t), (0, y), (w - 1, y))
    return surf


def make_horizontal_gradient(size: Tuple[int, int], left: Color, right: Color) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size)
    if w <= 1:
        surf.fill(left)
        return surf
    for x in range(w):
        t = x / (w - 1)
        pygame.draw.line(surf, lerp_color(left, right, t), (x, 0), (x, h - 1))
    return surf


def brick_dimensions() -> Tuple[int, int]:
    total_w = SCREEN_W - 2 * BRICK_MARGIN_X
    cell = (total_w - (BRICK_COLS - 1) * BRICK_GAP) / BRICK_COLS
    return int(cell), BRICK_H


def draw_radial_ball(
    target: pygame.Surface,
    cx: int,
    cy: int,
    radius: int,
    core: Color,
    edge: Color,
) -> None:
    if radius <= 0:
        return
    steps = max(radius, 6)
    for i in range(steps, 0, -1):
        t = i / steps
        col = lerp_color(core, edge, t)
        pygame.draw.circle(target, col, (cx, cy), max(1, int(radius * t)))


class GameState(Enum):
    PLAYING = auto()
    WON = auto()
    LOST = auto()


@dataclass
class Brick:
    rect: pygame.Rect
    alive: bool
    special: bool  # при разрушении даёт падающий бонус


@dataclass
class PowerUp:
    """Падающая точка: поймать платформой — увеличить ширину."""

    x: float
    y: float
    radius: float = 6.0
    active: bool = True


class Paddle:
    def __init__(self) -> None:
        w = PADDLE_INITIAL_W
        self._width = float(w)
        self.rect = pygame.Rect(0, PADDLE_Y, w, PADDLE_H)
        self.rect.centerx = SCREEN_W // 2

    @property
    def width(self) -> float:
        return self._width

    def grow(self) -> None:
        new_w = min(
            self._width * PADDLE_GROWTH,
            SCREEN_W * PADDLE_MAX_W_FRACTION,
        )
        cx = self.rect.centerx
        self._width = new_w
        self.rect.width = int(round(new_w))
        self.rect.centerx = cx
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_W, SCREEN_H))

    def move(self, dx: float, dt: float) -> None:
        self.rect.x += int(round(dx * dt))
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_W, SCREEN_H))


class Ball:
    def __init__(self) -> None:
        self.x = SCREEN_W / 2.0
        self.y = PADDLE_Y - BALL_RADIUS - 2
        angle = random.uniform(-math.pi * 0.85, -math.pi * 0.15)
        self.vx = math.cos(angle) * BALL_SPEED
        self.vy = math.sin(angle) * BALL_SPEED

    def center(self) -> Tuple[float, float]:
        return self.x, self.y


def circle_rect_resolve(
    cx: float,
    cy: float,
    r: float,
    rect: pygame.Rect,
) -> Optional[Tuple[float, float, str]]:
    """
    Если круг пересекает прямоугольник, возвращает (нов_cx, new_cy, нормаль 'left'|'right'|'top'|'bottom')
    для выталкивания и отражения. Иначе None.
    """
    closest_x = max(rect.left, min(cx, rect.right))
    closest_y = max(rect.top, min(cy, rect.bottom))
    dx = cx - closest_x
    dy = cy - closest_y
    dist_sq = dx * dx + dy * dy
    if dist_sq >= r * r:
        return None

    # ближайшая грань: по минимальному проникновению
    dist_left = cx - rect.left
    dist_right = rect.right - cx
    dist_top = cy - rect.top
    dist_bottom = rect.bottom - cy

    m = min(dist_left, dist_right, dist_top, dist_bottom)
    if m == dist_left:
        side = "left"
        new_cx = rect.left - r
    elif m == dist_right:
        side = "right"
        new_cx = rect.right + r
    elif m == dist_top:
        side = "top"
        new_cy = rect.top - r
    else:
        side = "bottom"
        new_cy = rect.bottom + r

    if m == dist_left or m == dist_right:
        new_cy = cy
        return new_cx, new_cy, side
    new_cx = cx
    return new_cx, new_cy, side


def reflect_velocity(
    vx: float,
    vy: float,
    side: str,
) -> Tuple[float, float]:
    if side in ("left", "right"):
        return -vx, vy
    return vx, -vy


def build_bricks() -> List[Brick]:
    total_w = SCREEN_W - 2 * BRICK_MARGIN_X
    cell = (total_w - (BRICK_COLS - 1) * BRICK_GAP) / BRICK_COLS
    bricks: List[Brick] = []
    indices = list(range(BRICK_ROWS * BRICK_COLS))
    random.shuffle(indices)
    num_special = max(1, int(len(indices) * SPECIAL_BRICK_FRACTION))
    special_set = set(indices[:num_special])

    idx = 0
    for row in range(BRICK_ROWS):
        for col in range(BRICK_COLS):
            x = BRICK_MARGIN_X + col * (cell + BRICK_GAP)
            y = BRICK_TOP + row * (BRICK_H + BRICK_GAP)
            r = pygame.Rect(int(x), int(y), int(cell), BRICK_H)
            bricks.append(
                Brick(rect=r, alive=True, special=(idx in special_set))
            )
            idx += 1
    return bricks


def bricks_remaining(bricks: Sequence[Brick]) -> int:
    return sum(1 for b in bricks if b.alive)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Arkada")

    bg = make_vertical_gradient((SCREEN_W, SCREEN_H), UI_BG_TOP, UI_BG_BOTTOM)
    bw, bh = brick_dimensions()
    brick_surf_normal = make_vertical_gradient((bw, bh), UI_BRICK_TOP, UI_BRICK_BOTTOM)
    brick_surf_special = make_vertical_gradient(
        (bw, bh), UI_BRICK_SPECIAL_TOP, UI_BRICK_SPECIAL_BOTTOM
    )
    paddle_grad_src = make_horizontal_gradient(
        (256, PADDLE_H), UI_PADDLE_LEFT, UI_PADDLE_RIGHT
    )

    hud_h = 44
    hud_bar = make_vertical_gradient((SCREEN_W, hud_h), (36, 40, 60), (20, 22, 36))
    vignette = pygame.Surface((SCREEN_W, 100), pygame.SRCALPHA)
    for y in range(100):
        a = int(55 * (y / 99.0) ** 1.2)
        pygame.draw.line(vignette, (0, 0, 0, a), (0, y), (SCREEN_W - 1, y))

    end_veil = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    for y in range(SCREEN_H):
        t = (y / max(SCREEN_H - 1, 1)) ** 0.85
        a = int(70 + 120 * t)
        pygame.draw.line(end_veil, (10, 12, 22, a), (0, y), (SCREEN_W - 1, y))

    clock = pygame.time.Clock()

    font = pygame.font.SysFont("segoeui", 22)
    font_title = pygame.font.SysFont("segoeui", 24, bold=True)

    paddle = Paddle()
    ball = Ball()
    bricks = build_bricks()
    powerups: List[PowerUp] = []

    state = GameState.PLAYING
    keys_held = {pygame.K_LEFT: False, pygame.K_RIGHT: False}

    while True:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key in keys_held:
                    keys_held[event.key] = True
                if event.key == pygame.K_r and state != GameState.PLAYING:
                    paddle = Paddle()
                    ball = Ball()
                    bricks = build_bricks()
                    powerups.clear()
                    state = GameState.PLAYING
            if event.type == pygame.KEYUP:
                if event.key in keys_held:
                    keys_held[event.key] = False

        if state == GameState.PLAYING:
            dx = 0.0
            if keys_held[pygame.K_LEFT]:
                dx -= 1.0
            if keys_held[pygame.K_RIGHT]:
                dx += 1.0
            paddle.move(dx * PADDLE_SPEED, dt)

            # мяч
            ball.x += ball.vx * dt
            ball.y += ball.vy * dt

            # стены
            if ball.x - BALL_RADIUS <= 0:
                ball.x = BALL_RADIUS
                ball.vx = abs(ball.vx)
            elif ball.x + BALL_RADIUS >= SCREEN_W:
                ball.x = SCREEN_W - BALL_RADIUS
                ball.vx = -abs(ball.vx)
            if ball.y - BALL_RADIUS <= 0:
                ball.y = BALL_RADIUS
                ball.vy = abs(ball.vy)

            # проигрыш
            if ball.y - BALL_RADIUS > SCREEN_H:
                state = GameState.LOST

            # платформа
            if state == GameState.PLAYING:
                resolved = circle_rect_resolve(
                    ball.x, ball.y, BALL_RADIUS, paddle.rect
                )
                if resolved is not None:
                    new_x, new_y, side = resolved
                    ball.x, ball.y = new_x, new_y
                    if side == "top":
                        # отскок с учётом позиции удара по платформе
                        rel = (ball.x - paddle.rect.centerx) / (paddle.rect.width / 2.0)
                        rel = max(-1.0, min(1.0, rel))
                        angle = rel * (math.pi / 3)
                        speed = math.hypot(ball.vx, ball.vy)
                        if speed < 1:
                            speed = BALL_SPEED
                        ball.vx = math.sin(angle) * speed
                        ball.vy = -abs(math.cos(angle) * speed)
                    else:
                        ball.vx, ball.vy = reflect_velocity(ball.vx, ball.vy, side)

            # кирпичи
            if state == GameState.PLAYING:
                for b in bricks:
                    if not b.alive:
                        continue
                    res = circle_rect_resolve(ball.x, ball.y, BALL_RADIUS, b.rect)
                    if res is None:
                        continue
                    nx, ny, side = res
                    ball.x, ball.y = nx, ny
                    ball.vx, ball.vy = reflect_velocity(ball.vx, ball.vy, side)
                    b.alive = False
                    if b.special:
                        powerups.append(
                            PowerUp(
                                x=float(b.rect.centerx),
                                y=float(b.rect.centery),
                            )
                        )
                    break

            if state == GameState.PLAYING and bricks_remaining(bricks) == 0:
                state = GameState.WON

            # бонусы
            if state == GameState.PLAYING:
                for p in powerups:
                    if not p.active:
                        continue
                    p.y += POWERUP_FALL_SPEED * dt
                    if p.y - p.radius > SCREEN_H:
                        p.active = False
                        continue
                    pr = pygame.Rect(
                        int(p.x - p.radius),
                        int(p.y - p.radius),
                        int(2 * p.radius),
                        int(2 * p.radius),
                    )
                    if pr.colliderect(paddle.rect):
                        paddle.grow()
                        p.active = False

        screen.blit(bg, (0, 0))

        for b in bricks:
            if not b.alive:
                continue
            img = brick_surf_special if b.special else brick_surf_normal
            screen.blit(img, b.rect.topleft)
            shade = lerp_color(UI_BRICK_BOTTOM, (18, 20, 30), 0.35)
            pygame.draw.line(
                screen,
                shade,
                (b.rect.left, b.rect.bottom - 1),
                (b.rect.right - 1, b.rect.bottom - 1),
            )

        pw, ph = paddle.rect.size
        paddle_draw = pygame.transform.smoothscale(paddle_grad_src, (max(1, pw), ph))
        screen.blit(paddle_draw, paddle.rect.topleft)
        hi = lerp_color(UI_PADDLE_LEFT, (255, 255, 255), 0.45)
        pygame.draw.line(
            screen,
            hi,
            (paddle.rect.left + 1, paddle.rect.top),
            (paddle.rect.right - 2, paddle.rect.top),
        )
        lo = lerp_color(UI_PADDLE_RIGHT, (24, 26, 38), 0.5)
        pygame.draw.line(
            screen,
            lo,
            (paddle.rect.left + 1, paddle.rect.bottom - 1),
            (paddle.rect.right - 2, paddle.rect.bottom - 1),
        )

        draw_radial_ball(
            screen,
            int(ball.x),
            int(ball.y),
            BALL_RADIUS,
            UI_BALL_CORE,
            UI_BALL_EDGE,
        )
        gloss = lerp_color(UI_BALL_CORE, (255, 255, 255), 0.55)
        pygame.draw.circle(
            screen,
            gloss,
            (int(ball.x) - 2, int(ball.y) - 2),
            max(2, BALL_RADIUS // 3),
        )

        for p in powerups:
            if p.active:
                draw_radial_ball(
                    screen,
                    int(p.x),
                    int(p.y),
                    int(p.radius),
                    UI_POWER_CORE,
                    UI_POWER_EDGE,
                )

        screen.blit(vignette, (0, SCREEN_H - vignette.get_height()))
        screen.blit(hud_bar, (0, 0))

        if state == GameState.WON:
            screen.blit(end_veil, (0, 0))
            line = "Все кирпичи сбиты"
            sub = "R — новая партия"
            title = font_title.render(line, True, UI_TEXT_ACCENT)
            st = font.render(sub, True, UI_TEXT_DIM)
            tx = SCREEN_W // 2 - title.get_width() // 2
            ty = SCREEN_H // 2 - title.get_height() // 2 - 8
            screen.blit(font_title.render(line, True, (14, 16, 28)), (tx + 2, ty + 2))
            screen.blit(title, (tx, ty))
            sx = SCREEN_W // 2 - st.get_width() // 2
            sy = ty + title.get_height() + 10
            screen.blit(st, (sx, sy))
        elif state == GameState.LOST:
            screen.blit(end_veil, (0, 0))
            line = "Мяч утерян"
            sub = "R — заново"
            title = font_title.render(line, True, (255, 210, 210))
            st = font.render(sub, True, UI_TEXT_DIM)
            tx = SCREEN_W // 2 - title.get_width() // 2
            ty = SCREEN_H // 2 - title.get_height() // 2 - 8
            screen.blit(font_title.render(line, True, (48, 22, 28)), (tx + 2, ty + 2))
            screen.blit(title, (tx, ty))
            sx = SCREEN_W // 2 - st.get_width() // 2
            sy = ty + title.get_height() + 10
            screen.blit(st, (sx, sy))

        hint = font.render("← → движение    R рестарт", True, UI_TEXT_DIM)
        screen.blit(hint, (14, 12))

        pygame.display.flip()


if __name__ == "__main__":
    main()
