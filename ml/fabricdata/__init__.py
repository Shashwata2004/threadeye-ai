"""Builds the ThreadEye detector's training data from public fabric-defect datasets (see ml/DATASETS.md).

readers (one per source) → class mapping → near-duplicate grouping → group-aware split → tiles → COCO export.
"""
