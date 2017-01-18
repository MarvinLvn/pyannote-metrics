#!/usr/bin/env python
# encoding: utf-8

# The MIT License (MIT)

# Copyright (c) 2012-2017 CNRS

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# AUTHORS
# Hervé BREDIN - http://herve.niderb.fr

from __future__ import unicode_literals
from __future__ import print_function


import scipy.stats
import numpy as np
import pandas as pd
import multiprocessing


class BaseMetric(object):
    """
    :class:`BaseMetric` is the base class for most PyAnnote evaluation metrics.

    Parameters
    ----------
    name : str
        Human-readable name of the metric (eg. 'diarization error rate')
    components : list, set or tuple
        Human-readable names of the components of the metric
        (eg. ['correct', 'false alarm', 'miss', 'confusion'])

    """

    @classmethod
    def metric_name(cls):
        raise NotImplementedError(
            cls.__name__ + " is missing a 'metric_name' class method. "
            "It should return the name of the metric as string.")

    @classmethod
    def metric_components(cls):
        raise NotImplementedError(
            cls.__name__ + " is missing a 'metric_components' class method. "
            "It should return the list of names of metric components.")

    def __init__(self, **kwargs):
        super(BaseMetric, self).__init__()
        self.manager_ = multiprocessing.Manager()
        self.metric_name_ = self.__class__.metric_name()
        self.components_ = set(self.__class__.metric_components())
        self.reset()

    def init_components(self):
        return {value: 0. for value in self.components_}

    def reset(self):
        """Reset accumulated components and metric values"""
        self.accumulated_ = self.manager_.dict()
        for value in self.components_:
            self.accumulated_[value] = 0.
        self.results_ = self.manager_.list()

    def __get_name(self):
        return self.__class__.metric_name()
    name = property(fget=__get_name, doc="Metric name.")

    def __call__(self, reference, hypothesis, detailed=False, **kwargs):
        """Compute metric value and accumulate components

        Parameters
        ----------
        reference : type depends on the metric
            Manual `reference`
        hypothesis : same as `reference`
            Evaluated `hypothesis`
        detailed : bool, optional
            By default (False), return metric value only.

            Set `detailed` to True to return dictionary where keys are
            components names and values are component values

        Returns
        -------
        value : float (if `detailed` is False)
            Metric value
        components : dict (if `detailed` is True)
            `components` updated with metric value

        """

        # compute metric components
        components = self.compute_components(reference, hypothesis, **kwargs)

        # compute rate based on components
        components[self.metric_name_] = self.compute_metric(components)

        # keep track of this computation
        self.results_.append((reference.uri, components))

        # accumulate components
        for name in self.components_:
            self.accumulated_[name] += components[name]

        if detailed:
            return components

        return components[self.metric_name_]

    def report(self, display=False):
        """Evaluation report

        Parameters
        ----------
        display : bool, optional
            Set to True to print the report to stdout.

        Returns
        -------
        report : pandas.DataFrame
            Dataframe with one column per metric component, one row per
            evaluated item, and one final row for accumulated results.
        """

        report = []
        uris = []

        for uri, components in self.results_:
            row = {}
            total = components['total']
            for key, value in components.items():
                if key == self.name:
                    row[key, '(percent)'] = 100 * value
                elif key == 'total':
                    row[key, '(seconds)'] = value
                else:
                    row[key, '(seconds)'] = value
                    row[key, '(percent)'] = 100 * value / total

            report.append(row)
            uris.append(uri)

        row = {}
        components = self.accumulated_
        total = components['total']
        for key, value in components.items():
            if key == self.name:
                row[key, '(percent)'] = 100 * value
            elif key == 'total':
                row[key, '(seconds)'] = value
            else:
                row[key, '(seconds)'] = value
                row[key, '(percent)'] = 100 * value / total
        row[self.name, '(percent)'] = 100 * abs(self)
        report.append(row)
        uris.append('TOTAL')

        df = pd.DataFrame(report)

        df['item'] = uris
        df = df.set_index('item')

        df.columns = pd.MultiIndex.from_tuples(df.columns)

        if display:
            print(df.to_string(index=True, sparsify=False, justify='right', float_format=lambda f: '{0:.2f}'.format(f)))

        return df

    def __str__(self):
        report = self.report(display=False)
        return report.to_string(
            sparsify=False,
            float_format=lambda f: '{0:.2f}'.format(f))

    def __abs__(self):
        """Compute metric value from accumulated components"""
        return self.compute_metric(self.accumulated_)

    def __getitem__(self, component):
        """Get value of accumulated `component`.

        Parameters
        ----------
        component : str
            Name of `component`

        Returns
        -------
        value : type depends on the metric
            Value of accumulated `component`

        """
        if component == slice(None, None, None):
            return dict(self.accumulated_)
        else:
            return self.accumulated_[component]

    def __iter__(self):
        """Iterator over the accumulated (uri, value)"""
        for uri, component in self.results_:
            yield uri, component

    def compute_components(self, reference, hypothesis, **kwargs):
        """Compute metric components

        Parameters
        ----------
        reference : type depends on the metric
            Manual `reference`
        hypothesis : same as `reference`
            Evaluated `hypothesis`

        Returns
        -------
        components : dict
            Dictionary where keys are component names and values are component
            values

        """
        raise NotImplementedError(
            cls.__name__ + " is missing a 'compute_components' method."
            "It should return a dictionary where keys are component names "
            "and values are component values.")

    def compute_metric(self, components):
        """Compute metric value from computed `components`

        Parameters
        ----------
        components : dict
            Dictionary where keys are components names and values are component
            values

        Returns
        -------
        value : type depends on the metric
            Metric value
        """
        raise NotImplementedError(
            cls.__name__ + " is missing a 'compute_metric' method. "
            "It should return the actual value of the metric based "
            "on the precomputed component dictionary given as input.")

    def confidence_interval(self, alpha=0.9):
        """Compute confidence interval on accumulated metric values

        Parameters
        ----------
        alpha : float, optional
            Probability that the returned confidence interval contains
            the true metric value.

        Returns
        -------
        (center, (lower, upper))
            with center the mean of the conditional pdf of the metric value
            and (lower, upper) is a confidence interval centered on the median,
            containing the estimate to a probability alpha.

        See Also:
        ---------
        scipy.stats.bayes_mvs

        """
        m, _, _ = scipy.stats.bayes_mvs(
            [r[self.metric_name_] for _, r in self.results_], alpha=alpha)
        return m


PRECISION_NAME = 'precision'
PRECISION_RETRIEVED = '# retrieved'
PRECISION_RELEVANT_RETRIEVED = '# relevant retrieved'


class Precision(BaseMetric):
    """
    :class:`Precision` is a base class for precision-like evaluation metrics.

    It defines two components '# retrieved' and '# relevant retrieved' and the
    compute_metric() method to compute the actual precision:

        Precision = # retrieved / # relevant retrieved

    Inheriting classes must implement compute_components().
    """

    @classmethod
    def metric_name(cls):
        return PRECISION_NAME

    @classmethod
    def metric_components(cls):
        return [PRECISION_RETRIEVED, PRECISION_RELEVANT_RETRIEVED]

    def compute_metric(self, components):
        """Compute precision from `components`"""
        numerator = components[PRECISION_RELEVANT_RETRIEVED]
        denominator = components[PRECISION_RETRIEVED]
        if denominator == 0.:
            if numerator == 0:
                return 1.
            else:
                raise ValueError('')
        else:
            return numerator/denominator

RECALL_NAME = 'recall'
RECALL_RELEVANT = '# relevant'
RECALL_RELEVANT_RETRIEVED = '# relevant retrieved'


class Recall(BaseMetric):
    """
    :class:`Recall` is a base class for recall-like evaluation metrics.

    It defines two components '# relevant' and '# relevant retrieved' and the
    compute_metric() method to compute the actual recall:

        Recall = # relevant retrieved / # relevant

    Inheriting classes must implement compute_components().
    """

    @classmethod
    def metric_name(cls):
        return RECALL_NAME

    @classmethod
    def metric_components(cls):
        return [RECALL_RELEVANT, RECALL_RELEVANT_RETRIEVED]

    def compute_metric(self, components):
        """Compute recall from `components`"""
        numerator = components[RECALL_RELEVANT_RETRIEVED]
        denominator = components[RECALL_RELEVANT]
        if denominator == 0.:
            if numerator == 0:
                return 1.
            else:
                raise ValueError('')
        else:
            return numerator/denominator


def f_measure(precision, recall, beta=1.):
    """Compute f-measure

    f-measure is defined as follows:
        F(P, R, b) = (1+b²).P.R / (b².P + R)

    where P is `precision`, R is `recall` and b is `beta`
    """
    return (1+beta*beta)*precision*recall / (beta*beta*precision+recall)
