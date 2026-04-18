"""
Простая аркада: платформа, мяч, кирпичи, бонусы с цветных кирпичей.
Зависимость: pip install pygame
Стиль отрисовки намеренно минимальный — только логика и базовая визуализация.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Sequence, Tuple

import pygame


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
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_W - self.rect.width, SCREEN_H))


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
    pygame.display.set_caption("Arkada (logic)")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 22)

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

        # отрисовка (заглушка)
        screen.fill((24, 24, 28))
        for b in bricks:
            if b.alive:
                color = (180, 90, 90) if b.special else (140, 140, 150)
                pygame.draw.rect(screen, color, b.rect)
        pygame.draw.rect(screen, (200, 200, 220), paddle.rect)
        pygame.draw.circle(
            screen, (240, 240, 100), (int(ball.x), int(ball.y)), BALL_RADIUS
        )
        for p in powerups:
            if p.active:
                pygame.draw.circle(
                    screen, (80, 200, 255), (int(p.x), int(p.y)), int(p.radius)
                )

        if state == GameState.WON:
            msg = font.render("Победа: все кирпичи сбиты (R — заново)", True, (255, 255, 255))
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2))
        elif state == GameState.LOST:
            msg = font.render("Мяч утерян (R — заново)", True, (255, 200, 200))
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2))

        hint = font.render("Стрелки ← →   R рестарт", True, (160, 160, 170))
        screen.blit(hint, (8, 8))

        pygame.display.flip()


if __name__ == "__main__":
    main()
