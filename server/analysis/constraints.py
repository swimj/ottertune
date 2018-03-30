#
# OtterTune - constraints.py
#
# Copyright (c) 2017-18, Carnegie Mellon University Database Group
#
'''
Created on Sep 8, 2016

@author: dvanaken
'''

import copy
import numpy as np


class ParamConstraintHelper(object):

    @property
    def num_categorical_params(self):
        return len(self.encoder_.n_values)

    def __init__(self, scaler, encoder):
        if 'inverse_transform' not in dir(scaler):
            raise Exception("Scaler object must provide function inverse_transform(X)")
        if 'transform' not in dir(scaler):
            raise Exception("Scaler object must provide function transform(X)")
        self.scaler_ = scaler
        self.encoder_ = encoder.encoder

    def apply_constraints(self, sample, scaled=True, rescale=True):
        conv_sample = self._handle_scaling(sample, scaled)

        n_values = self.encoder_.n_values_
        cat_start_indices = self.encoder_.feature_indices_
        for i, nvals in enumerate(n_values):
            start_idx = cat_start_indices[i]
            cvals = conv_sample[start_idx: start_idx + nvals]
            cvals = np.array(np.arange(nvals) == np.argmax(cvals), dtype=float)
            assert np.sum(cvals) == 1
            conv_sample[start_idx: start_idx + nvals] = cvals
        conv_sample = self._handle_rescaling(conv_sample, rescale)
        return conv_sample

    def _handle_scaling(self, sample, scaled):
        if scaled:
            if sample.ndim == 1:
                sample = sample.reshape(1, -1)
            sample = self.scaler_.inverse_transform(sample).ravel()
        else:
            sample = np.array(sample)
        return sample

    def _handle_rescaling(self, sample, rescale):
        if rescale:
            if sample.ndim == 1:
                sample = sample.reshape(1, -1)
            return self.scaler_.transform(sample).ravel()
        return sample

    def get_valid_config(self, sample, scaled=True, rescale=True):
        conv_sample = self._handle_scaling(sample, scaled)

        for i, (param, param_val) in enumerate(zip(self.params_, conv_sample)):
            if param.isinteger:
                conv_sample[i] = round(param_val)

        conv_sample = self.apply_constraints(conv_sample,
                                             scaled=False,
                                             rescale=False)

        if conv_sample.ndim == 1:
            conv_sample = conv_sample.reshape(1, -1)
        if self.encoder_ is not None:
            conv_sample = self.encoder_.inverse_transform(conv_sample)

        conv_sample = self._handle_rescaling(conv_sample.squeeze(), rescale)
        return conv_sample

    def randomize_categorical_features(self, sample, scaled=True, rescale=True):
        n_values = self.encoder_.n_values_
        cat_start_indices = self.encoder_.feature_indices_
        n_cat_feats = len(n_values)

        if n_cat_feats == 0:
            return sample

        conv_sample = self._handle_scaling(sample, scaled)
        flips = np.zeros((n_cat_feats,), dtype=bool)

        # Always flip at least one categorical feature
        flips[0] = True

        # Flip the rest with decreasing probability
        p = 0.3
        for i in range(1, n_cat_feats):
            if np.random.rand() <= p:
                flips[i] = True
            p *= 0.5

        flip_shuffle_indices = np.random.choice(np.arange(n_cat_feats),
                                                n_cat_feats,
                                                replace=False)
        flips = flips[flip_shuffle_indices]

        for i, nvals in enumerate(n_values):
            if flips[i]:
                start_idx = cat_start_indices[i]
                current_val = conv_sample[start_idx: start_idx + nvals]
                assert np.all(np.logical_or(current_val == 0, current_val == 1)), \
                    "categorical {0}: value not 0/1: {1}".format(i, current_val)
                choices = np.arange(nvals)[current_val != 1]
                assert choices.size == nvals - 1
                r = np.zeros(nvals)
                r[np.random.choice(choices)] = 1
                assert np.sum(r) == 1
                conv_sample[start_idx: start_idx + nvals] = r

        conv_sample = self._handle_rescaling(conv_sample, rescale)
        return conv_sample

    def get_numerical_mask(self):
        mask = []
        current_idx, cat_idx = 0, 0
        for param in self.params_:
            if param.iscategorical:
                if param.isboolean:
                    mask.append(False)
                    current_idx += 1
                else:
                    assert current_idx == self.encoder_.xform_start_indices[cat_idx]
                    nvals = self.encoder_.n_values[cat_idx]
                    mask.extend([False for _ in range(nvals)])
                    cat_idx += 1
                    current_idx += nvals
            else:
                mask.append(True)
                current_idx += 1
        return np.array(mask)

    def get_combinations_size(self):
        if self.num_categorical_params == 0:
            return 0
        cat_count = 0
        current_idx, cat_idx = 0, 0
        for param in self.params_:
            if param.iscategorical:
                if param.isboolean:
                    cat_count += 1
                    current_idx += 1
                else:
                    assert current_idx == self.encoder_.xform_start_indices[cat_idx]
                    nvals = self.encoder_.n_values[cat_idx]
                    cat_count += nvals
                    cat_idx += 1
                    current_idx += nvals
            else:
                current_idx += 1
        assert cat_count > 0
        return 2 ** cat_count

    def get_grid(self, max_size=2048):
        import itertools

        possible_combos = self.get_combinations_size()
        assert possible_combos > 0
        num_columns = int(np.log2(possible_combos))
        if possible_combos > max_size:
            # Grid too large so sample instead
            combo_grid = np.random.binomial(1, 0.5, (max_size, num_columns))
        else:
            # Get entire grid
            combo_grid = list(itertools.product([0, 1], repeat=num_columns))
            assert len(combo_grid) == possible_combos
            combo_grid = np.array(combo_grid)
        # Scale the grid
        cat_mask = ~self.get_numerical_mask()

        X_scaler_cat = copy.deepcopy(self.scaler_)
        X_scaler_cat.mean_ = X_scaler_cat.mean_[cat_mask]
        X_scaler_cat.scale_ = X_scaler_cat.scale_[cat_mask]
        X_scaler_cat.var_ = X_scaler_cat.var_[cat_mask]
        combo_grid = X_scaler_cat.transform(combo_grid)
        return combo_grid

    def merge_grid(self, combo_grid, numeric_param_conf):
        nrows = combo_grid.shape[0]
        ncols = combo_grid.shape[1] + numeric_param_conf.shape[0]
        data_grid = np.ones((nrows, ncols)) * np.nan

        num_mask = self.get_numerical_mask()
        assert num_mask.shape[0] == ncols
        combo_idx, conf_idx = 0, 0
        for i, isnumeric in enumerate(num_mask):
            if isnumeric:
                data_grid[:, i] = numeric_param_conf[conf_idx]
                conf_idx += 1
            else:
                data_grid[:, i] = combo_grid[:, combo_idx]
                combo_idx += 1
        assert np.all(np.isfinite(data_grid))
        return data_grid
