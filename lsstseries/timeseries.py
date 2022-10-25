import pandas as pd
import numpy as np


class timeseries():
    """represent and analyze Rubin timeseries data"""
    def __init__(self, data=None):
        self.data = data
        self.meta = {'id': None} # metadata dict
        self.colmap = {'time': None, 'flux': None, 'flux_err': None} # column mapping

    # I/O
    def from_dict(self, data_dict, time_label='time', flux_label='flux', err_label='flux_err', 
                  band_label='band'):
        """Build dataframe from a python dictionary

        Parameters
        ----------
        data_dict : `dict`
            Dictionary contaning the data
        time_label: `str`
            Name for column containing time information
        flux_label: `str`
            Name for column containing signal (flux, magnitude, etc) information
        err_label: `str`
            Name for column containing error information
        band_label: `str`
            Name for column containing filter information
        """

        try:
            data_dict[band_label]
        except KeyError:
            raise KeyError(f"The indicated label '{band_label}' was not found.")
        index = self._build_index(data_dict[band_label])
        data_dict = {key: data_dict[key] for key in data_dict if key != band_label}
        self.data = pd.DataFrame(data=data_dict, index=index).sort_index()

        labels = [time_label, flux_label, err_label]
        
        for label, quantity in zip(labels, list(self.colmap.keys())):

            if (quantity == 'flux_err') and (label is None): # flux_err is optional
                continue

            try:
                self.data[label]
                self.colmap[quantity] = label
            except KeyError:
                raise KeyError(f"The indicated label '{label}' was not found.")
            
        return self      

    def _from_ensemble(self, data, object_id, time_label='time', flux_label='flux', err_label='flux_err'):
        """Loader function for inputing data from an ensemble"""
        self.cols = list(data.columns)
        self.data = data
        self.meta['id'] = object_id

        labels = [time_label, flux_label, err_label]
        
        for label, quantity in zip(labels, list(self.colmap.keys())):

            if (quantity == 'flux_err') and (label is None): # flux_err is optional
                continue

            try:
                self.data[label]
                self.colmap[quantity] = label
            except KeyError:
                raise KeyError(f"The indicated label '{label}' was not found.")

        return self

    @property
    def time(self):
        """Time values stored as a Pandas Series"""
        return self.data[self.colmap['time']]

    @property
    def flux(self):
        """Flux values stored as a Pandas Series"""
        return self.data[self.colmap['flux']]

    @property
    def flux_err(self):
        """Flux error values stored as a Pandas Series"""
        if self.colmap['flux_err'] is not None: # Errors are not mandatory
            return self.data[self.colmap['flux_err']]
        else:
            return None

    @property
    def band(self):
        """Band labels stored as a Pandas Index"""
        return self.data.index.get_level_values('band')

    def _build_index(self, band):
        """Build pandas multiindex from band array"""
        # Create a multiindex
        tuples = zip(band, range(len(band)))
        index = pd.MultiIndex.from_tuples(tuples, names=["band", "index"])
        return index

    def stetson_J_multi(self):
        unq_band = np.unique(self.band)
        result = {}
        # TODO: ability to remove nan values
        for band in unq_band:
            fluxes = self.data.loc[band]['psFlux'].values
            errors = self.data.loc[band]['psFluxErr'].values
            result[band] = self.stetson_J(fluxes, errors)
        return result

    def stetson_J(self, fluxes, errors):
        """Compute the single band stetsonJ statistic.

        Parameters
        ----------
        fluxes : `numpy.ndarray` (N,)
            Calibrated lightcurve flux values.
        errors : `numpy.ndarray` (N,)
            Errors on the calibrated lightcurve fluxes.
        mean : `float`
            Starting mean from previous plugin.

        Returns
        -------
        stetsonJ : `float`
            stetsonJ statistic for the input fluxes and errors.

        References
        ----------
        .. [1] Stetson, P. B., "On the Automatic Determination of Light-Curve
        Parameters for Cepheid Variables", PASP, 108, 851S, 1996

        Notes
        ----------
        Taken from
        https://github.com/lsst/meas_base/blob/main/python/lsst/meas/base/diaCalculationPlugins.py
        """
        mean = None

        n_points = len(fluxes)
        flux_mean = self._stetson_mean(fluxes, errors, mean)
        delta_val = (
            np.sqrt(n_points / (n_points - 1)) * (fluxes - flux_mean) / errors)
        p_k = delta_val ** 2 - 1

        return np.mean(np.sign(p_k) * np.sqrt(np.fabs(p_k)))

    def _stetson_mean(self,
                      values,
                      errors,
                      mean=None,
                      alpha=2.,
                      beta=2.,
                      n_iter=20,
                      tol=1e-6):
        """Compute the stetson mean of the fluxes which down-weights outliers.

        Weighted biased on an error weighted difference scaled by a constant
        (1/``a``) and raised to the power beta. Higher betas more harshly
        penalize outliers and ``a`` sets the number of sigma where a weighted
        difference of 1 occurs.

        Parameters
        ----------
        values : `numpy.dnarray`, (N,)
            Input values to compute the mean of.
        errors : `numpy.ndarray`, (N,)
            Errors on the input values.
        mean : `float`
            Starting mean value or None.
        alpha : `float`
            Scalar down-weighting of the fractional difference. lower->more
            clipping. (Default value is 2.)
        beta : `float`
            Power law slope of the used to down-weight outliers. higher->more
            clipping. (Default value is 2.)
        n_iter : `int`
            Number of iterations of clipping.
        tol : `float`
            Fractional and absolute tolerance goal on the change in the mean
            before exiting early. (Default value is 1e-6)

        Returns
        -------
        mean : `float`
            Weighted stetson mean result.

        References
        ----------
        .. [1] Stetson, P. B., "On the Automatic Determination of Light-Curve
        Parameters for Cepheid Variables", PASP, 108, 851S, 1996

        Notes
        ----------
        Taken from
        https://github.com/lsst/meas_base/blob/main/python/lsst/meas/base/diaCalculationPlugins.py
        """
        n_points = len(values)
        n_factor = np.sqrt(n_points / (n_points - 1))
        inv_var = 1 / errors ** 2

        if mean is None:
            mean = np.average(values, weights=inv_var)
        for iter_idx in range(n_iter):
            chi = np.fabs(n_factor * (values - mean) / errors)
            tmp_mean = np.average(
                values,
                weights=inv_var / (1 + (chi / alpha) ** beta))
            diff = np.fabs(tmp_mean - mean)
            mean = tmp_mean
            if diff / mean < tol and diff < tol:
                break
        return mean
