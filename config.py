#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конфигурация системы OCTO-PI
Автоматическое определение ОС и настройка параметров
"""

import platform
import os

# Определяем операционную систему
SYSTEM = platform.system()  # 'Windows', 'Linux', 'Darwin' (macOS)

# Индексы камер в зависимости от ОС
if SYSTEM == 'Linux':
    # Linux (Ubuntu и др.) - камеры на чётных индексах
    CAMERA_INDICES = [0, 2, 4, 6]
elif SYSTEM == 'Windows':
    # Windows - стандартные индексы
    CAMERA_INDICES = [0, 1, 2, 3]
elif SYSTEM == 'Darwin':
    # macOS - обычно как Windows
    CAMERA_INDICES = [0, 1, 2, 3]
else:
    # По умолчанию
    CAMERA_INDICES = [0, 1, 2, 3]

# Количество камер
NUM_CAMERAS = len(CAMERA_INDICES)

# Маппинг: логический индекс (0-3) -> физический индекс камеры
# Например, на Linux: камера 0 -> /dev/video0, камера 1 -> /dev/video2
CAMERA_MAP = {i: CAMERA_INDICES[i] for i in range(NUM_CAMERAS)}

# Обратный маппинг: физический индекс -> логический индекс
CAMERA_MAP_REVERSE = {v: k for k, v in CAMERA_MAP.items()}


def get_camera_indices():
    """Получить список индексов камер для текущей ОС"""
    return CAMERA_INDICES.copy()


def get_physical_camera_index(logical_index):
    """Преобразовать логический индекс (0-3) в физический индекс камеры"""
    if logical_index < NUM_CAMERAS:
        return CAMERA_INDICES[logical_index]
    return logical_index


def get_logical_camera_index(physical_index):
    """Преобразовать физический индекс камеры в логический (0-3)"""
    return CAMERA_MAP_REVERSE.get(physical_index, physical_index)


# Вывод информации при импорте (для отладки)
if __name__ == '__main__':
    print(f"Операционная система: {SYSTEM}")
    print(f"Индексы камер: {CAMERA_INDICES}")
    print(f"Маппинг камер: {CAMERA_MAP}")
else:
    from loguru import logger
    logger.info(f"Platform: {SYSTEM}, Camera indices: {CAMERA_INDICES}")

