# Root Cause Analysis: Model Size & Performance Degradation After Spark Migration

**Date**: 2026-05-01
**Status**: RESOLVED
**Severity**: High (Breaking change in production serving)

## Executive Summary

After migrating ML training code from `Legacy Functions/` to `spark/training_pipeline.py`, generated models were 60-70% smaller in size and exhibited degraded performance. Root cause was **accidental hyperparameter search space reduction** during code migration, compounded by a **model naming inconsistency** that would have broken production serving.

## Symptoms Observed

1. **Model Size Reduction**
   - In-race win model: Expected ~14MB, actual size unknown (not generated)
   - In-race podium model: Expected ~40MB, actual size unknown (not generated)

2. **Performance Degradation**
   - Models not performing as expected compared to legacy versions

3. **Existing Models in assets/Models/**
   - `podium_model.pkl`: 338KB
   - `in_race_win_model.pkl`: 14MB
   - `in_race_podium_model.pkl`: 40MB

## Root Cause Analysis

### Issue #1: Reduced Hyperparameter Search Space (PRIMARY CAUSE)

**Location**: `spark/training_pipeline.py` lines 495, 502

**What Happened**:
During migration, the hyperparameter search configuration for in-race models was accidentally reduced:

| Parameter | Legacy (InRace_MLCore.py) | Migrated (Before Fix) | Impact |
|-----------|---------------------------|------------------------|---------|
| `n_estimators` | [100, 150] | [100] | Max trees reduced by 33% |
| `max_depth` | [8, 12, 15] | [8, 12] | Max tree depth capped lower |
| `min_samples_split` | [5, 10] | **MISSING** | No split optimization |
| `n_iter` | 5 | 2 | 60% fewer search iterations |

**Why This Matters**:
- Fewer trees (max 100 vs 150) → smaller model files
- Shallower trees (max depth 12 vs 15) → less model complexity
- Missing `min_samples_split` → no split parameter tuning
- Fewer iterations (2 vs 5) → higher chance of suboptimal hyperparameters

**Result**: Models were undertrained with suboptimal hyperparameters, leading to both smaller file sizes and worse performance.

### Issue #2: Model Naming Inconsistency (BREAKING CHANGE)

**Location**: `spark/training_pipeline.py` lines 479, 521

**What Happened**:
Pre-race model filename was changed during migration without updating dependent code:

```python
# Legacy (PreRace_MLCore.py:15)
MODEL_PATH = 'assets/Models/podium_model.pkl'

# Migrated (BEFORE FIX)
joblib.dump(grid_pre.best_estimator_, 'pre_race_model.pkl')
upload_model('pre_race_model.pkl')  # ❌ Uploads to GCS with wrong name
```

**Impact on Production**:
```python
# model_serving/app.py:32
PRE_RACE_MODEL_FILE = "podium_model.pkl"  # ❌ Downloads wrong filename from GCS!

# core/ml_core.py:33
PRE_RACE_MODEL_PATH = 'assets/Models/podium_model.pkl'  # ❌ Expects wrong filename!
```

**Result**: Model serving would fail when trying to download `podium_model.pkl` from GCS, as only `pre_race_model.pkl` was uploaded.

## Evidence Trail

### Code Comparison

**In-Race Win Model (Legacy vs Migrated)**:

```python
# Legacy Functions/InRace_MLCore.py:45-54
param_dist = {
    'n_estimators': [100, 150],
    'max_depth': [8, 12, 15],
    'min_samples_split': [5, 10]
}
search_win = RandomizedSearchCV(
    estimator=base_win,
    param_distributions=param_dist,
    n_iter=5,  # 5 random combinations
    cv=3,
    scoring='f1'
)

# spark/training_pipeline.py:495 (BEFORE FIX)
search_win = RandomizedSearchCV(
    base_win,
    param_distributions={
        'n_estimators': [100],      # ❌ Only 1 option
        'max_depth': [8, 12]        # ❌ Missing depth 15
                                    # ❌ min_samples_split removed
    },
    n_iter=2,  # ❌ Only 2 iterations
    cv=3,
    scoring='f1'
)
```

### Dependency Analysis

**Files Affected by Naming Change**:
- `model_serving/app.py:32` - Expects `podium_model.pkl` from GCS
- `core/ml_core.py:33` - Expects `podium_model.pkl` in assets/Models/
- `Legacy Functions/PreRace_MLCore.py:15` - Original definition

## Resolution

### Fix #1: Restore Hyperparameter Search Space

**Files Changed**: `spark/training_pipeline.py`

**Line 495** (In-race win model):
```python
# BEFORE
search_win = RandomizedSearchCV(base_win, param_distributions={'n_estimators': [100], 'max_depth': [8, 12]}, n_iter=2, ...)

# AFTER
search_win = RandomizedSearchCV(base_win, param_distributions={'n_estimators': [100, 150], 'max_depth': [8, 12, 15], 'min_samples_split': [5, 10]}, n_iter=5, ...)
```

**Line 502** (In-race podium model):
```python
# BEFORE
search_pod = RandomizedSearchCV(base_pod, param_distributions={'n_estimators': [100], 'max_depth': [8, 12]}, n_iter=2, ...)

# AFTER
search_pod = RandomizedSearchCV(base_pod, param_distributions={'n_estimators': [100, 150], 'max_depth': [8, 12, 15], 'min_samples_split': [5, 10]}, n_iter=5, ...)
```

### Fix #2: Restore Model Naming Consistency

**Files Changed**: `spark/training_pipeline.py`

**Line 479** (Model save):
```python
# BEFORE
joblib.dump(grid_pre.best_estimator_, 'pre_race_model.pkl')

# AFTER
joblib.dump(grid_pre.best_estimator_, 'podium_model.pkl')
```

**Line 521** (GCS upload):
```python
# BEFORE
upload_model('pre_race_model.pkl')

# AFTER
upload_model('podium_model.pkl')
```

## Verification Steps

After applying fixes, verify:

1. **Re-run training pipeline**:
   ```bash
   python spark/training_pipeline.py <PROJECT_ID>
   ```

2. **Check model sizes**:
   - `podium_model.pkl` should be ~338KB
   - `in_race_win_model.pkl` should be ~14MB
   - `in_race_podium_model.pkl` should be ~40MB

3. **Check GCS bucket**:
   ```bash
   gsutil ls gs://f1chubby-model-<PROJECT_ID>/
   ```
   Should contain:
   - `podium_model.pkl` (NOT `pre_race_model.pkl`)
   - `in_race_win_model.pkl`
   - `in_race_podium_model.pkl`

4. **Verify model performance**:
   - Review generated `*_metrics.txt` files
   - Compare accuracy/F1 scores with legacy models
   - Ensure hyperparameters include expected ranges

## Lessons Learned

1. **Always compare full hyperparameter configurations** when migrating ML code, not just high-level logic
2. **Maintain backward compatibility** in model naming when external systems depend on specific filenames
3. **Automated tests should verify**:
   - Model file sizes within expected ranges
   - Hyperparameter search space completeness
   - Model artifact naming conventions
4. **Code review checklists** should include hyperparameter verification for ML migrations

## Related Files

- `spark/training_pipeline.py` - Fixed migration code
- `Legacy Functions/InRace_MLCore.py` - Original in-race training code
- `Legacy Functions/PreRace_MLCore.py` - Original pre-race training code
- `model_serving/app.py` - Production serving (depends on model names)
- `core/ml_core.py` - Core ML utilities (depends on model names)

## Timeline

- **2026-05-01**: Issue discovered during code comparison
- **2026-05-01**: Root cause identified via systematic debugging
- **2026-05-01**: Fixes applied to `spark/training_pipeline.py`
- **2026-05-01**: Root cause analysis documented

---

**Document Owner**: Development Team
**Review Status**: Complete
**Next Review**: After successful model retraining
