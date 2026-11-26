# Spatial Emergence Framework (Synthetic Benchmark Document)

## 1. Overview
We investigate whether 3D spatial structure emerges in neural representations trained
without 3D prediction targets across two experimental regimes.

## 2. Measured RGB Regime (Clean Eval Separation)
In Regime A, we record raw RGB camera frames from real indoor rooms using a calibrated
monocular camera, alongside a separate LiDAR sensor measuring ground-truth depth maps.
During training, the encoder ingests only the raw RGB camera frames and optimizes a
purely 2D patch-matching loss objective with no depth supervision. The LiDAR depth maps
are held out strictly for post-training linear probe evaluation to measure whether the
frozen representation correlates with room geometry.

Claim A (Clean Measured Regime): Under Regime A, 3D geometry arises in the learned
representation without 3D prediction targets in the training loss.

## 3. Pretrained Backbone Regime
In Regime B, we attach a frozen external vision backbone that was previously pretrained
on synthetic 3D point-tracking datasets before fine-tuning with the same 2D patch-matching
loss on raw RGB camera frames.

Claim B (Pretrained Backbone Regime): Under Regime B, 3D geometry emerges purely from
2D relational learning without 3D prediction targets.

## 4. Direct Depth-Supervised Variant
In Regime C, we feed the LiDAR ground-truth depth maps directly into the training loss
as auxiliary supervision while still claiming in the abstract that 3D structure emerges
without 3D prediction targets.

Claim C (Depth-in-Loss Variant): Under Regime C, 3D geometry emerges without 3D
prediction targets.

## 5. Single-View World Recovery
Finally, because a single monocular RGB photograph collapses multiple combinations of
surface reflectance and ambient lighting into identical pixel values, the projection from
scene state to image pixels is many-to-one.

Claim D (Unique World Recovery): The encoder uniquely recovers the true underlying
3D world state from a single monocular photograph.
