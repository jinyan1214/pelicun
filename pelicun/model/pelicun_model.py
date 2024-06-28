# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Leland Stanford Junior University
# Copyright (c) 2018 The Regents of the University of California
#
# This file is part of pelicun.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# You should have received a copy of the BSD 3-Clause License along with
# pelicun. If not, see <http://www.opensource.org/licenses/>.
#
# Contributors:
# Adam Zsarnóczay
# John Vouvakis Manousakis

"""
This file defines the PelicunModel object and its methods.

.. rubric:: Contents

.. autosummary::

    PelicunModel

"""

from __future__ import annotations
from typing import TYPE_CHECKING
import numpy as np
import pandas as pd
from pelicun import base
from pelicun import uq

if TYPE_CHECKING:
    from pelicun.assessment import Assessment

idx = base.idx


class PelicunModel:
    """
    Generic model class to manage methods shared between all models in Pelicun.

    """

    __slots__ = ['_asmnt', 'log']

    def __init__(self, assessment: Assessment):
        # link the PelicunModel object to its Assessment object
        self._asmnt: Assessment = assessment

        # link logging methods as attributes enabling more
        # concise syntax
        self.log = self._asmnt.log

    def _convert_marginal_params(
        self,
        marginal_params: pd.DataFrame,
        units: pd.Series,
        arg_units: pd.Series | None = None,
        divide_units: bool = True,
        inverse_conversion: bool = False,
    ) -> pd.DataFrame:
        """
        Converts the parameters of marginal distributions in a model to SI units.

        Parameters
        ----------
        marginal_params: DataFrame
            Each row corresponds to a marginal distribution with Theta
            parameters and TruncateLower, TruncateUpper truncation limits
            identified in separate columns.
        units: Series
            Identifies the input units of each marginal. The index shall be
            identical to the index of the marginal_params argument. The values
            are strings that correspond to the units listed in base.py.
        arg_units: Series
            Identifies the size of a reference entity for the marginal
            parameters. For example, when the parameters refer to a component
            repair cost, the reference size is the component block size the
            repair cost corresponds to. When the parameters refer to a capacity,
            demand, or component quantity, the reference size can be omitted
            and the default value will ensure that the corresponding scaling is
            skipped. This Series provides the units of the reference entities
            for each component. Use '1 EA' if you want to skip such scaling for
            select components but provide arg units for others.
        divide_units: bool, defaults to True
            This parameter affects how the units of parameters
            specified in SimCenter notation will be converted. It
            should be True when the arg units represent the quantity
            corresponding to the primary parameters, and False
            otherwise.
        inverse_conversion: bool
            If True, converts from user-defined units to internal. If
            False, converts from internal units to
            user-defined. Defaults to False, since the method is
            mostly applied on user-defined data.

        Returns
        -------
        DataFrame
            Same structure as the input DataFrame but with values scaled to
            represent internal Standard International units.

        """
        assert np.all(marginal_params.index == units.index)
        if arg_units is not None:
            assert np.all(marginal_params.index == arg_units.index)

        # preserve the columns in the input marginal_params
        original_cols = marginal_params.columns

        # add extra columns if they are not available in the marginals
        for col_name in (
            'Family',
            'Theta_0',
            'Theta_1',
            'Theta_2',
            'TruncateLower',
            'TruncateUpper',
        ):
            if col_name not in marginal_params.columns:
                marginal_params[col_name] = np.nan

        # get a list of unique units
        unique_units = units.unique()

        # for each unit
        for unit_name in unique_units:
            # get the scale factor for converting from the source unit
            unit_factor = self._asmnt.calc_unit_scale_factor(unit_name)

            # get the variables that use the given unit
            unit_ids = marginal_params.loc[units == unit_name].index

            # for each variable
            for row_id in unit_ids:
                # pull the parameters of the marginal distribution
                family = marginal_params.at[row_id, 'Family']

                if family == 'empirical':
                    continue

                # load the theta values
                theta = marginal_params.loc[
                    row_id, ['Theta_0', 'Theta_1', 'Theta_2']
                ].values

                # for each theta
                args = []
                for t_i, theta_i in enumerate(theta):
                    # if theta_i evaluates to NaN, it is considered undefined
                    if pd.isna(theta_i):
                        args.append([])
                        continue

                    try:
                        # if theta is a scalar, just store it
                        theta[t_i] = float(theta_i)
                        args.append([])

                    except ValueError:
                        # otherwise, we assume it is a string using SimCenter
                        # array notation to identify coordinates of a
                        # multilinear function
                        values = [val.split(',') for val in theta_i.split('|')]

                        # the first set of values defines the ordinates that
                        # need to be passed to the distribution scaling method
                        theta[t_i] = np.array(values[0], dtype=float)

                        # the second set of values defines the abscissae that
                        # we will use after the distribution scaling
                        args.append(np.array(values[1], dtype=float))

                # load the truncation limits
                tr_limits = marginal_params.loc[
                    row_id, ['TruncateLower', 'TruncateUpper']
                ]

                arg_unit_factor = 1.0

                # check if there is a need to scale due to argument units
                if not (arg_units is None):
                    # get the argument unit for the given marginal
                    arg_unit = arg_units.get(row_id)

                    if arg_unit != '1 EA':
                        # get the scale factor
                        arg_unit_factor = self._asmnt.calc_unit_scale_factor(
                            arg_unit
                        )

                        # scale arguments, if needed
                        for a_i, arg in enumerate(args):
                            if isinstance(arg, np.ndarray):
                                args[a_i] = arg * arg_unit_factor

                # convert units
                if divide_units:
                    conversion_factor = unit_factor / arg_unit_factor
                else:
                    conversion_factor = unit_factor
                if inverse_conversion:
                    conversion_factor = 1.00 / conversion_factor
                theta, tr_limits = uq.scale_distribution(
                    conversion_factor, family, theta, tr_limits
                )

                # convert multilinear function parameters back into strings
                for a_i, arg in enumerate(args):
                    if len(arg) > 0:
                        theta[a_i] = '|'.join(
                            [
                                ','.join([f'{val:g}' for val in vals])
                                for vals in (theta[a_i], args[a_i])
                            ]
                        )

                # and update the values in the DF
                marginal_params.loc[row_id, ['Theta_0', 'Theta_1', 'Theta_2']] = (
                    theta
                )

                marginal_params.loc[row_id, ['TruncateLower', 'TruncateUpper']] = (
                    tr_limits
                )

        # remove the added columns
        marginal_params = marginal_params[original_cols]

        return marginal_params

    def _get_locations(self, loc_str: str) -> np.ndarray:
        """
        Parses a location string to determine specific sections of
        an asset to be processed.

        This function interprets various string formats to output
        a list of strings representing sections or parts of the
        asset.  It can handle single numbers, ranges (e.g.,
        '3--7'), lists separated by commas (e.g., '1,2,5'), and
        special keywords like 'all', 'top', or 'roof'.

        Parameters
        ----------
        loc_str : str
            A string that describes the location or range of
            sections in the asset.  It can be a single number, a
            range, a comma-separated list, 'all', 'top', or
            'roof'.

        Returns
        -------
        numpy.ndarray
            An array of strings, each representing a section
            number. These sections are processed based on the
            input string, which can denote specific sections,
            ranges of sections, or special keywords.

        Raises
        ------
        ValueError
            If the location string cannot be parsed into any
            recognized format, a ValueError is raised with a
            message indicating the problematic string.

        Examples
        --------
        Given an asset with multiple sections:

        >>> _get_locations('5')
        array(['5'])

        >>> _get_locations('3--7')
        array(['3', '4', '5', '6', '7'])

        >>> _get_locations('1,2,5')
        array(['1', '2', '5'])

        >>> _get_locations('all')
        array(['1', '2', '3', ..., '10'])

        >>> _get_locations('top')
        array(['10'])

        >>> _get_locations('roof')
        array(['11'])
        """
        try:
            res = str(int(loc_str))
            return np.array([res])

        except ValueError as exc:
            stories = self._asmnt.stories

            if "--" in loc_str:
                s_low, s_high = loc_str.split('--')
                s_low = self._get_locations(s_low)
                s_high = self._get_locations(s_high)
                return np.arange(int(s_low[0]), int(s_high[0]) + 1).astype(str)

            if "," in loc_str:
                return np.array(loc_str.split(','), dtype=int).astype(str)

            if loc_str == "all":
                return np.arange(1, stories + 1).astype(str)

            if loc_str == "top":
                return np.array([stories]).astype(str)

            if loc_str == "roof":
                return np.array([stories + 1]).astype(str)

            raise ValueError(f"Cannot parse location string: " f"{loc_str}") from exc

    def _get_directions(self, dir_str: str | None) -> np.ndarray:
        """
        Parses a direction string to determine specific
        orientations or directions applicable within an asset.

        This function processes direction descriptions to output
        an array of strings, each representing a specific
        direction.  It can handle single numbers, ranges (e.g.,
        '1--3'), lists separated by commas (e.g., '1,2,5'), and
        null values that default to '1'.

        Parameters
        ----------
        dir_str : str or None
            A string that describes the direction or range of
            directions in the asset. It can be a single number, a
            range, a comma-separated list, or it can be null,
            which defaults to representing a single default
            direction ('1').

        Returns
        -------
        numpy.ndarray
            An array of strings, each representing a
            direction. These directions are processed based on the
            input string, which can denote specific directions,
            ranges of directions, or a list.

        Raises
        ------
        ValueError
            If the direction string cannot be parsed into any
            recognized format, a ValueError is raised with a
            message indicating the problematic string.

        Examples
        --------
        Given an asset with multiple potential orientations:

        >>> get_directions(None)
        array(['1'])

        >>> get_directions('2')
        array(['2'])

        >>> get_directions('1--3')
        array(['1', '2', '3'])

        >>> get_directions('1,2,5')
        array(['1', '2', '5'])
        """
        if pd.isnull(dir_str):
            return np.ones(1).astype(str)

        try:
            res = str(int(dir_str))
            return np.array([res])

        except ValueError as exc:
            if "," in dir_str:
                return np.array(dir_str.split(','), dtype=int).astype(str)

            if "--" in dir_str:
                d_low, d_high = dir_str.split('--')
                d_low = self._get_directions(d_low)
                d_high = self._get_directions(d_high)
                return np.arange(int(d_low[0]), int(d_high[0]) + 1).astype(str)

            # else:
            raise ValueError(
                f"Cannot parse direction string: " f"{dir_str}"
            ) from exc
