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
This module defines constants, basic classes and methods for pelicun.

.. rubric:: Contents

.. autosummary::

    load_default_options
    update_vals
    merge_default_config
    convert_to_SimpleIndex
    convert_to_MultiIndex
    show_matrix
    describe
    str2bool
    float_or_None
    int_or_None
    process_loc
    dedupe_index
    dict_raise_on_duplicates
    parse_units
    convert_units

    Options
    Logger

"""

from __future__ import annotations
from typing import Any
from typing import TYPE_CHECKING
from collections.abc import Callable
import os
import sys
from datetime import datetime
import json
import warnings
from pathlib import Path
import argparse
import pprint
import numpy as np
from scipy.interpolate import interp1d  # type: ignore
import pandas as pd
import colorama
from colorama import Fore
from colorama import Style
from pelicun.warnings import PelicunWarning

if TYPE_CHECKING:
    from pelicun.assessment import Assessment


colorama.init()
# set printing options
pp = pprint.PrettyPrinter(indent=2, width=80 - 24)

pd.options.display.max_rows = 20
pd.options.display.max_columns = None  # type: ignore
pd.options.display.expand_frame_repr = True
pd.options.display.width = 300

idx = pd.IndexSlice


class Options:
    """
    Options objects store analysis options and the logging
    configuration.

    Attributes
    ----------
    sampling_method: str
        Sampling method to use. Specified in the user's configuration
        dictionary, otherwise left as provided in the default configuration
        file (see settings/default_config.json in the pelicun source
        code). Can be any of ['LHS', 'LHS_midpoint',
        'MonteCarlo']. The default is 'LHS'.
    units_file: str
        Location of a user-specified units file, which should contain
        the names of supported units and their conversion factors (the
        value some quantity of a given unit needs to be multiplied to
        be expressed in the base units). Value specified in the user
        configuration dictionary. Pelicun comes with a set of default
        units which are always loaded (see settings/default_units.json
        in the pelicun source code). Units specified in the units_file
        overwrite the default units.
    demand_offset: dict
        Demand offsets are used in the process of mapping a component
        location to its associated EDP. This allows components that
        are sensitive to EDPs of different levels to be specified as
        present at the same location (e.g. think of desktop computer
        and suspended ceiling, both at the same story). Each
        component's offset value is specified in the component
        fragility database. This setting applies a supplemental global
        offset to specific EDP types. The value is specified in the
        user's configuration dictionary, otherwise left as provided in
        the default configuration file (see
        settings/default_config.json in the pelicun source code).
    nondir_multi_dict: dict
        Nondirectional components are sensitive to demands coming in
        any direction. Results are typically available in two
        orthogonal directions. FEMA P-58 suggests using the formula
        `max(dir_1, dir_2) * 1.2` to estimate the demand for such
        components. This parameter allows modifying the 1.2 multiplier
        with a user-specified value. The change can be applied to
        "ALL" EDPs, or for specific EDPs, such as "PFA", "PFV",
        etc. The value is specified in the user's configuration
        dictionary, otherwise left as provided in the default
        configuration file (see settings/default_config.json in the
        pelicun source code).
    rho_cost_time: float
        Specifies the correlation between the repair cost and repair
        time consequences. The value is specified in the user's
        configuration dictionary, otherwise left as provided in the
        default configuration file (see
        "RepairCostAndTimeCorrelation") (see
        settings/default_config.json in the pelicun source code).
    eco_scale: dict
        Controls how the effects of economies of scale are handled in
        the damaged component quantity aggregation for loss measure
        estimation. The dictionary is specified in the user's
        configuration dictionary, otherwise left as provided in the
        default configuration file (see settings/default_config.json
        in the pelicun source code).
    log: Logger
        Logger object. Configuration parameters coming from the user's
        configuration dictionary or the default configuration file
        control logging behavior. See Logger class.

    """

    __slots__ = [
        '_asmnt',
        'defaults',
        'sampling_method',
        'list_all_ds',
        '_seed',
        '_rng',
        'units_file',
        'demand_offset',
        'nondir_multi_dict',
        'rho_cost_time',
        'eco_scale',
        'log',
    ]

    def __init__(
        self,
        user_config_options: dict[str, Any] | None,
        assessment: Assessment | None = None,
    ):
        """
        Initializes an Options object.

        Parameters
        ----------
        user_config_options: dict, Optional
            User-specified configuration dictionary. Any provided
            user_config_options override the defaults.
        assessment: Assessment, Optional
            Assessment object that will be using this Options
            object. If it is not intended to use this Options object
            for an Assessment (e.g. defining an Options object for UQ
            use), this value should be None.
        """

        self._asmnt = assessment

        self.defaults: dict[str, Any] | None = None
        self.sampling_method: str | None = None
        self.list_all_ds: bool | None = None

        self._seed: float | None = None

        self._rng = np.random.default_rng()
        merged_config_options = merge_default_config(user_config_options)

        self._seed = merged_config_options['Seed']
        self.sampling_method = merged_config_options['Sampling']['SamplingMethod']
        self.list_all_ds = merged_config_options['ListAllDamageStates']

        self.units_file = merged_config_options['UnitsFile']

        self.demand_offset = merged_config_options['DemandOffset']
        self.nondir_multi_dict = merged_config_options['NonDirectionalMultipliers']
        self.rho_cost_time = merged_config_options['RepairCostAndTimeCorrelation']
        self.eco_scale = merged_config_options['EconomiesOfScale']

        # instantiate a Logger object with the finalized configuration
        self.log = Logger(
            merged_config_options['Verbose'],
            merged_config_options['LogShowMS'],
            merged_config_options['LogFile'],
            merged_config_options['PrintLog'],
        )

    @property
    def seed(self) -> float | None:
        """
        Seed property

        Returns
        -------
        float
            Seed value
        """
        return self._seed

    @seed.setter
    def seed(self, value: float) -> None:
        """
        seed property setter
        """
        self._seed = value
        self._rng = np.random.default_rng(self._seed)  # type: ignore

    @property
    def rng(self) -> np.random.Generator:
        """
        rng property

        Returns
        -------
        Generator
            Random generator
        """
        return self._rng


class Logger:
    """
    Logger objects are used to generate log files documenting
    execution events and related messages.

    Attributes
    ----------
    verbose: bool
        If True, the pelicun echoes more information throughout the
        assessment.  This can be useful for debugging purposes. The
        value is specified in the user's configuration dictionary,
        otherwise left as provided in the default configuration file
        (see settings/default_config.json in the pelicun source code).
    log_show_ms: bool
        If True, the timestamps in the log file are in microsecond
        precision. The value is specified in the user's configuration
        dictionary, otherwise left as provided in the default
        configuration file (see settings/default_config.json in the
        pelicun source code).
    log_file: str, optional
        If a value is provided, the log is written to that file. The
        value is specified in the user's configuration dictionary,
        otherwise left as provided in the default configuration file
        (see settings/default_config.json in the pelicun source code).
    print_log: bool
        If True, the log is also printed to standard output. The
        value is specified in the user's configuration dictionary,
        otherwise left as provided in the default configuration file
        (see settings/default_config.json in the pelicun source code).

    """

    __slots__ = [
        'verbose',
        'log_show_ms',
        'log_file',
        'warning_file',
        'print_log',
        'warning_stack',
        'emitted',
        'log_time_format',
        'spaces',
        'log_div',
    ]

    def __init__(
        self, verbose: bool, log_show_ms: bool, log_file: str | None, print_log: bool
    ):
        """
        Initializes a Logger object.

        Parameters
        ----------
        see attributes of the Logger class.

        """
        self.verbose = verbose
        self.log_show_ms = bool(log_show_ms)

        if log_file is None:
            self.log_file = None
            self.warning_file = None
        else:
            try:
                path = Path(log_file)
                self.log_file = str(path.resolve())
                name, extension = split_file_name(self.log_file)
                self.warning_file = (
                    path.parent / (name + '_warnings' + extension)
                ).resolve()
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.write('')
                with open(self.warning_file, 'w', encoding='utf-8') as f:
                    f.write('')
            except BaseException as err:
                print(
                    f"{Fore.RED}WARNING: The filepath provided for the log file "
                    f"does not point to a valid location: {log_file}. \nPelicun "
                    f"cannot print the log to a file.\n"
                    f"The error was: '{err}'{Style.RESET_ALL}"
                )
                raise

        self.print_log = str2bool(print_log)
        self.warning_stack: list[str] = []
        self.emitted: set[str] = set()
        self.reset_log_strings()
        control_warnings()

    def reset_log_strings(self) -> None:
        """
        Populates the string-related attributes of the logger
        """

        if self.log_show_ms:
            self.log_time_format = '%H:%M:%S:%f'
            # the length of the time string in the log file
            self.spaces = ' ' * 16
            # to have a total length of 80 with the time added
            self.log_div = '-' * (80 - 17)
        else:
            self.log_time_format = '%H:%M:%S'
            self.spaces = ' ' * 9
            self.log_div = '-' * (80 - 10)

    def msg(
        self,
        msg: str = '',
        prepend_timestamp: bool = True,
        prepend_blank_space: bool = True,
    ) -> None:
        """
        Writes a message in the log file with the current time as prefix

        The time is in ISO-8601 format, e.g. 2018-06-16T20:24:04Z

        Parameters
        ----------
        msg: string
            Message to print.
        prepend_timestamp: bool
            Controls whether a timestamp is placed before the message.
        prepend_blank_space: bool
            Controls whether blank space is placed before the message.

        """

        # pylint: disable = consider-using-f-string
        msg_lines = msg.split('\n')

        for msg_i, msg_line in enumerate(msg_lines):
            if prepend_timestamp and (msg_i == 0):
                formatted_msg = '{} {}'.format(
                    datetime.now().strftime(self.log_time_format), msg_line
                )
            elif prepend_timestamp:
                formatted_msg = self.spaces + msg_line
            elif prepend_blank_space:
                formatted_msg = self.spaces + msg_line
            else:
                formatted_msg = msg_line

            if self.print_log:
                print(formatted_msg)

            if self.log_file is not None:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write('\n' + formatted_msg)

    def add_warning(self, msg: str) -> None:
        """
        Adds a warning to the warning stack.

        Note
        ----
        Warnings are only emitted when `emit_warnings` is called.

        Parameters
        ----------
        msg: str
            The warning message.

        """
        msg_lines = msg.split('\n')
        formatted_msg = '\n'
        for msg_line in msg_lines:
            formatted_msg += (
                self.spaces + Fore.RED + msg_line + Style.RESET_ALL + '\n'
            )
        if formatted_msg not in self.warning_stack:
            self.warning_stack.append(formatted_msg)

    def emit_warnings(self) -> None:
        """
        Issues all warnings and clears the warning stack.

        """
        for message in self.warning_stack:
            if message not in self.emitted:
                warnings.warn(message, PelicunWarning, stacklevel=2)
                if self.warning_file is not None:
                    with open(self.warning_file, 'a', encoding='utf-8') as f:
                        f.write(
                            message.replace(Fore.RED, '')
                            .replace(Style.RESET_ALL, '')
                            .replace(self.spaces, '')
                        )

        self.emitted = self.emitted.union(set(self.warning_stack))
        self.warning_stack = []

    def warn(self, msg: str) -> None:
        """
        Add an emit a warning immediately.

        Parameters
        ----------
        msg: str
            Warning message

        """
        self.add_warning(msg)
        self.emit_warnings()

    def div(self, prepend_timestamp: bool = False) -> None:
        """
        Adds a divider line in the log file
        """

        if prepend_timestamp:
            msg = self.log_div
        else:
            msg = '-' * 80
        self.msg(msg, prepend_timestamp=prepend_timestamp)

    def print_system_info(self) -> None:
        """
        Writes system information in the log.
        """

        self.msg(
            'System Information:', prepend_timestamp=False, prepend_blank_space=False
        )
        self.msg(
            f'local time zone: {datetime.utcnow().astimezone().tzinfo}\n'
            f'start time: {datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}\n'
            f'python: {sys.version}\n'
            f'numpy: {np.__version__}\n'
            f'pandas: {pd.__version__}\n',
            prepend_timestamp=False,
        )


# get the absolute path of the pelicun directory
pelicun_path = Path(os.path.dirname(os.path.abspath(__file__)))


def split_file_name(file_path: str) -> tuple[str, str]:
    """
    Separates a file name from the extension accounting for the case
    where the file name itself contains periods.

    Parameters
    ----------
    file_path: str
        Original file path.

    Returns
    -------
    tuple
        name: str
            Name of the file.
        extension: str
            File extension.

    """
    path = Path(file_path)
    name = path.stem
    extension = path.suffix
    return name, extension


def control_warnings() -> None:
    """
    Convenience function to turn warnings on/off

        See also: `pelicun/pytest.ini`. Devs: make sure to update that
        file when addressing & eliminating warnings.

    """
    if not sys.warnoptions:

        # Here we specify *specific* warnings to ignore.
        # 'message' -- a regex that the warning message must match

        # Note: we ignore known warnings emitted from our dependencies
        # and plan to address them soon.

        warnings.filterwarnings(
            action='ignore', message=".*Use to_numeric without passing `errors`.*"
        )
        warnings.filterwarnings(
            action='ignore', message=".*errors='ignore' is deprecated.*"
        )
        warnings.filterwarnings(
            action='ignore',
            message=".*The previous implementation of stack is deprecated.*",
        )
        warnings.filterwarnings(
            action='ignore',
            message=".*Setting an item of incompatible dtype is deprecated.*",
        )
        warnings.filterwarnings(
            action='ignore',
            message=".*DataFrame.groupby with axis=1 is deprecated.*",
        )


def load_default_options() -> dict:
    """
    Load the default_config.json file to set options to default values

    Returns
    -------
    dict
        Default options
    """

    with open(
        pelicun_path / "settings/default_config.json", 'r', encoding='utf-8'
    ) as f:
        default_config = json.load(f)

    default_options = default_config['Options']
    return default_options


def update_vals(
    update: dict, primary: dict, update_path: str, primary_path: str
) -> None:
    """
    Updates the values of the `update` nested dictionary with
    those provided in the `primary` nested dictionary. If a key
    already exists in update, and does not map to another
    dictionary, the value is left unchanged.

    Parameters
    ----------
    update: dict
        Dictionary -which can contain nested dictionaries- to be
        updated based on the values of `primary`. New keys existing
        in `primary` are added to `update`. Values of which keys
        already exist in `primary` are left unchanged.
    primary: dict
        Dictionary -which can contain nested dictionaries- to
        be used to update the values of `update`.
    update_path: str
        Identifier for the update dictionary. Used to make error
        messages more meaningful.
    primary_path: str
        Identifier for the update dictionary. Used to make error
        messages more meaningful.

    Raises
    ------
    ValueError
      If primary[key] is dict but update[key] is not.
    ValueError
      If update[key] is dict but primary[key] is not.
    """

    # pylint: disable=else-if-used
    # (`consider using elif`)

    # we go over the keys of `primary`
    for key in primary:
        # if `primary[key]` is a dictionary:
        if isinstance(primary[key], dict):
            # if the same `key` does not exist in update,
            # we associate it with an empty dictionary.
            if key not in update:
                update[key] = {}
            # if it exists already, it should map to
            # a dictionary.
            elif not isinstance(update[key], dict):
                raise ValueError(
                    f'{update_path}["{key}"] '
                    'should map to a dictionary. '
                    'The specified value is '
                    f'{update_path}["{key}"] = {update[key]}, but '
                    f'the default value is '
                    f'{primary_path}["{key}"] = {primary[key]}. '
                    f'Please revise {update_path}["{key}"].'
                )
            # With both being dictionaries, we use recursion.
            update_vals(
                update[key],
                primary[key],
                f'{update_path}["{key}"]',
                f'{primary_path}["{key}"]',
            )
        # if `primary[key]` is NOT a dictionary:
        else:
            # if `key` does not exist in `update`, we add it, with
            # its corresponding value.
            if key not in update:
                update[key] = primary[key]
            else:
                # key exists in update and should be left alone,
                # but we must check that it's not a dict here:
                if isinstance(update[key], dict):
                    raise ValueError(
                        f'{update_path}["{key}"] '
                        'should not map to a dictionary. '
                        f'The specified value is '
                        f'{update_path}["{key}"] = {update[key]}, but '
                        f'the default value is '
                        f'{primary_path}["{key}"] = {primary[key]}. '
                        f'Please revise {update_path}["{key}"].'
                    )
    # pylint: enable=else-if-used


def merge_default_config(user_config: dict | None) -> dict:
    """
    Merge the user-specified config with the configuration defined in
    the default_config.json file. If the user-specified config does
    not include some option available in the default options, then the
    default option is used in the merged config.

    Parameters
    ----------
    user_config: dict
        User-specified configuration dictionary

    Returns
    -------
    dict
        Merged configuration dictionary
    """

    config = user_config  # start from the user's config
    default_config = load_default_options()

    if config is None:
        config = {}

    # We fill out the user's config with the values available in the
    # default config that were not set.
    # We use a recursive function to handle nesting.
    update_vals(config, default_config, 'user_settings', 'default_settings')

    return config


def convert_to_SimpleIndex(
    data: pd.DataFrame, axis: int = 0, inplace: bool = False
) -> pd.DataFrame:
    """
    Converts the index of a DataFrame to a simple, one-level index

    The target index uses standard SimCenter convention to identify
    different levels: a dash character ('-') is used to separate each
    level of the index.

    Parameters
    ----------
    data: DataFrame
        The DataFrame that will be modified.
    axis: int, optional, default:0
        Identifies if the index (0) or the columns (1) shall be
        edited.
    inplace: bool, optional, default:False
        If yes, the operation is performed directly on the input
        DataFrame and not on a copy of it.

    Returns
    -------
    DataFrame
        The modified DataFrame

    Raises
    ------
    ValueError
        When an invalid axis parameter is specified
    """

    if axis in {0, 1}:
        if inplace:
            data_mod = data
        else:
            data_mod = data.copy()

        if axis == 0:
            # only perform this if there are multiple levels
            if data.index.nlevels > 1:
                simple_name = '-'.join(
                    [n if n is not None else "" for n in data.index.names]
                )
                simple_index = [
                    '-'.join([str(id_i) for id_i in id]) for id in data.index
                ]

                data_mod.index = pd.Index(simple_index, name=simple_name)
                data_mod.index.name = simple_name

        elif axis == 1:
            # only perform this if there are multiple levels
            if data.columns.nlevels > 1:
                simple_name = '-'.join(
                    [n if n is not None else "" for n in data.columns.names]
                )
                simple_index = [
                    '-'.join([str(id_i) for id_i in id]) for id in data.columns
                ]

                data_mod.columns = pd.Index(simple_index, name=simple_name)
                data_mod.columns.name = simple_name

    else:
        raise ValueError(f"Invalid axis parameter: {axis}")

    return data_mod


def convert_to_MultiIndex(
    data: pd.DataFrame, axis: int = 0, inplace: bool = False
) -> pd.DataFrame:
    """
    Converts the index of a DataFrame to a MultiIndex

    We assume that the index uses standard SimCenter convention to
    identify different levels: a dash character ('-') is expected to
    separate each level of the index.

    Parameters
    ----------
    data: DataFrame
        The DataFrame that will be modified.
    axis: int, optional, default:0
        Identifies if the index (0) or the columns (1) shall be
        edited.
    inplace: bool, optional, default:False
        If yes, the operation is performed directly on the input
        DataFrame and not on a copy of it.

    Returns
    -------
    DataFrame
        The modified DataFrame.

    Raises
    ------
    ValueError
        If an invalid axis is specified.
    """

    # check if the requested axis is already a MultiIndex
    if ((axis == 0) and (isinstance(data.index, pd.MultiIndex))) or (
        (axis == 1) and (isinstance(data.columns, pd.MultiIndex))
    ):
        # if yes, return the data unchanged
        return data

    if axis == 0:
        index_labels = [str(label).split('-') for label in data.index]

    elif axis == 1:
        index_labels = [str(label).split('-') for label in data.columns]

    else:
        raise ValueError(f"Invalid axis parameter: {axis}")

    max_lbl_len = np.max([len(labels) for labels in index_labels])

    for l_i, labels in enumerate(index_labels):
        if len(labels) != max_lbl_len:
            labels += [
                '',
            ] * (max_lbl_len - len(labels))
            index_labels[l_i] = labels

    index_labels_np = np.array(index_labels)

    if index_labels_np.shape[1] > 1:
        if inplace:
            data_mod = data
        else:
            data_mod = data.copy()

        if axis == 0:
            data_mod.index = pd.MultiIndex.from_arrays(index_labels_np.T)

        else:
            data_mod.columns = pd.MultiIndex.from_arrays(index_labels_np.T)

        return data_mod

    return data


def convert_dtypes(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Convert columns to a numeric datatype whenever possible. The
    function replaces None with NA otherwise columns containing None
    would continue to have the `object` type

    Parameters
    ----------
    dataframe: DataFrame
        The DataFrame that will be modified.

    Returns
    -------
    DataFrame
        The modified DataFrame.

    """
    dataframe.fillna(value=np.nan, inplace=True)
    # note: `axis=0` applies the function to the columns
    # note: ignoring errors is a bad idea and should never be done. In
    # this case, however, that's not what we do, despite the name of
    # this parameter. We simply don't convert the dtype of columns
    # that cannot be interpreted as numeric. That's what
    # `errors='ignore'` does.
    # See:
    # https://pandas.pydata.org/docs/reference/api/pandas.to_numeric.html
    return dataframe.apply(
        lambda x: pd.to_numeric(x, errors='ignore'), axis=0  # type:ignore
    )


def show_matrix(data, use_describe=False):
    """
    Print a matrix in a nice way using a DataFrame.

    Parameters
    ----------
    data : array-like
        The matrix data to display. Can be any array-like structure
        that pandas can convert to a DataFrame.
    use_describe : bool, default: False
        If True, provides a descriptive statistical summary of the
        matrix including specified percentiles.
        If False, simply prints the matrix as is.

    """
    if use_describe:
        pp.pprint(
            pd.DataFrame(data).describe(percentiles=[0.01, 0.1, 0.5, 0.9, 0.99])
        )
    else:
        pp.pprint(pd.DataFrame(data))


def multiply_factor_multiple_levels(
    df: pd.DataFrame,
    conditions: dict,
    factor: float,
    axis: int = 0,
    raise_missing: bool = True,
) -> None:
    """
    Multiply a value to selected rows of a DataFrame that is indexed
    with a hierarchical index (pd.MultiIndex). The change is done in
    place.

    Parameters
    ----------
    df: pd.DataFrame
        The DataFrame to be modified.
    conditions: dict
        A dictionary mapping level names with a single value. Only the
        rows where the index levels have the provided values will be
        affected. The dictionary can be empty, in which case all rows
        will be affected, or contain only some levels and values, in
        which case only the matching rows will be affected.
    factor: float
        Scaling factor to use.
    axis: int
        With 0 the condition is checked against the DataFrame's index,
        otherwise with 1 it is checked against the DataFrame's
        columns.
    raise_missing: bool
        Raise an error if no rows are matching the given conditions.

    Raises
    ------
    ValueError
        If the provided `axis` values is not either 0 or 1.
    ValueError
        If there are no rows matching the conditions and raise_missing
        is True.

    """

    if axis == 0:
        idx_to_use = df.index
    elif axis == 1:
        idx_to_use = df.columns
    else:
        raise ValueError(f'Invalid axis: `{axis}`')

    mask = pd.Series(True, index=idx_to_use)

    # Apply each condition to update the mask
    for level, value in conditions.items():
        mask &= idx_to_use.get_level_values(level) == value

    # pylint: disable=singleton-comparison
    if np.all(mask == False) and raise_missing:  # noqa
        raise ValueError(f'No rows found matching the conditions: `{conditions}`')

    if axis == 0:
        df.iloc[mask.to_numpy()] *= factor
    else:
        df.iloc[:, mask.to_numpy()] *= factor


def _warning(
    message: str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: Any = None,
    line: Any = None,
) -> None:
    """
    Custom warning function to format and print warnings more
    attractively. This function modifies how warning messages are
    displayed, emphasizing the file path and line number from where
    the warning originated.

    Parameters
    ----------
    message : str
        The warning message to be displayed.
    category : Warning
        The category of the warning (unused, but required for
        compatibility with standard warning signature).
    filename : str
        The path of the file from which the warning is issued. The
        function simplifies the path for display.
    lineno : int
        The line number in the file at which the warning is issued.
    file : file-like object, optional
        The target file object to write the warning to (unused, but
        required for compatibility with standard warning signature).
    line : str, optional
        Line of code causing the warning (unused, but required for
        compatibility with standard warning signature).
    """
    # pylint:disable = unused-argument
    if category != PelicunWarning:
        if '\\' in filename:
            file_path = filename.split('\\')
        elif '/' in filename:
            file_path = filename.split('/')
        else:
            file_path = None

        if file_path is not None:
            python_file = '/'.join(file_path[-3:])
        else:
            python_file = filename
        print(f'WARNING in {python_file} at line {lineno}\n{message}\n')
    else:
        print(message)


warnings.showwarning = _warning  # type: ignore


def describe(
    df,
    percentiles=(
        0.001,
        0.023,
        0.10,
        0.159,
        0.5,
        0.841,
        0.90,
        0.977,
        0.999,
    ),
):
    """
    Provides extended descriptive statistics for given data, including
    percentiles and log standard deviation for applicable columns.

    This function accepts both pandas Series and DataFrame objects
    directly, or any array-like structure which can be converted to
    them. It calculates common descriptive statistics and optionally
    adds log standard deviation for columns where all values are
    positive.

    Parameters
    ----------
    df : pd.Series, pd.DataFrame, or array-like
        The data to describe. If array-like, it is converted to a
        DataFrame or Series before analysis.
    percentiles : tuple of float, optional
        Specific percentiles to include in the output. Default
        includes an extensive range tailored to provide a detailed
        summary.

    Returns
    -------
    pd.DataFrame
        A DataFrame containing the descriptive statistics of the input
        data, transposed so that each descriptive statistic is a row.
    """
    if not isinstance(df, (pd.Series, pd.DataFrame)):
        vals = df
        cols = np.arange(vals.shape[1]) if vals.ndim > 1 else 0

        if vals.ndim == 1:
            df = pd.Series(vals, name=cols)
        else:
            df = pd.DataFrame(vals, columns=cols)

    # convert Series into a DataFrame
    if isinstance(df, pd.Series):
        df = pd.DataFrame(df)

    desc = df.describe(list(percentiles)).T

    # add log standard deviation to the stats
    desc.insert(3, "log_std", np.nan)
    desc = desc.T

    for col in desc.columns:
        if np.min(df[col]) > 0.0:
            desc.loc['log_std', col] = np.std(np.log(df[col]), ddof=1)

    return desc


def str2bool(v: str | bool) -> bool:
    """
    Converts a string representation of truth to boolean True or
    False.

    This function is designed to convert string inputs that represent
    boolean values into actual Python boolean types. It handles
    typical representations of truthiness and falsiness, and is case
    insensitive.

    Parameters
    ----------
    v : str or bool
        The value to convert into a boolean. This can be a boolean
        itself (in which case it is simply returned) or a string that
        is expected to represent a boolean value.

    Returns
    -------
    bool
        The boolean value corresponding to the input.

    Raises
    ------
    argparse.ArgumentTypeError
        If `v` is a string that does not correspond to a boolean
        value, an error is raised indicating that a boolean value was
        expected.
    """
    # courtesy of Maxim @ Stackoverflow

    if isinstance(v, bool):
        return v
    if v.lower() in {'yes', 'true', 'True', 't', 'y', '1'}:
        return True
    if v.lower() in {'no', 'false', 'False', 'f', 'n', '0'}:
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')


def float_or_None(string: str) -> float | None:
    """
    This is a convenience function for converting strings to float or
    None

    Parameters
    ----------
    string: str
        A string

    Returns
    -------
    float or None
        A float, if the given string can be converted to a
        float. Otherwise, it returns None
    """
    try:
        res = float(string)
        return res
    except ValueError:
        return None


def int_or_None(string: str) -> int | None:
    """
    This is a convenience function for converting strings to int or
    None

    Parameters
    ----------
    string: str
        A string

    Returns
    -------
    int or None
        An int, if the given string can be converted to an
        int. Otherwise, it returns None
    """
    try:
        res = int(string)
        return res
    except ValueError:
        return None


def with_parsed_str_na_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a dataframe, this function identifies values that have
    string type and can be interpreted as N/A, and replaces them with
    actual NA's.

    Parameters
    ----------
    df: pd.DataFrame
        Dataframe to process

    Returns
    -------
    pd.DataFrame
        The dataframe with proper N/A values.

    """
    na_vals = {
        '',
        'N/A',
        '-1.#QNAN',
        'null',
        'None',
        '<NA>',
        'nan',
        '-NaN',
        '1.#IND',
        'NaN',
        '#NA',
        '1.#QNAN',
        'NULL',
        '-nan',
        '#N/A',
        '#N/A N/A',
        'n/a',
        '-1.#IND',
        'NA',
    }
    # obtained from Pandas' internal STR_NA_VALUES variable.

    # Replace string NA values with actual NaNs
    return df.apply(
        lambda col: col.map(
            lambda x: np.nan if isinstance(x, str) and x in na_vals else x
        )
    )


def dedupe_index(dataframe: pd.DataFrame, dtype: type = str) -> None:
    """
    Modifies the index of a DataFrame to ensure all index elements are
    unique by adding an extra level.  Assumes that the DataFrame's
    original index is a MultiIndex with specified names. A unique
    identifier ('uid') is added as an additional index level based on
    the cumulative count of occurrences of the original index
    combinations.

    Parameters
    ----------
    dataframe : pd.DataFrame
        The DataFrame whose index is to be modified. It must have a
        MultiIndex.
    dtype : type, optional
        The data type for the new index level 'uid'. Defaults to str.

    Notes
    -----
    This function changes the DataFrame in place, hence it does not
    return the DataFrame but modifies the original one provided.

    """
    inames = dataframe.index.names
    dataframe.reset_index(inplace=True)
    dataframe['uid'] = (dataframe.groupby([*inames]).cumcount()).astype(dtype)
    dataframe.set_index([*inames] + ['uid'], inplace=True)
    dataframe.sort_index(inplace=True)


# Input specs

EDP_to_demand_type = {
    # Drifts
    'Story Drift Ratio': 'PID',
    'Peak Interstory Drift Ratio': 'PID',
    'Roof Drift Ratio': 'PRD',
    'Peak Roof Drift Ratio': 'PRD',
    'Damageable Wall Drift': 'DWD',
    'Racking Drift Ratio': 'RDR',
    'Mega Drift Ratio': 'PMD',
    'Residual Drift Ratio': 'RID',
    'Residual Interstory Drift Ratio': 'RID',
    'Peak Effective Drift Ratio': 'EDR',
    # Floor response
    'Peak Floor Acceleration': 'PFA',
    'Peak Floor Velocity': 'PFV',
    'Peak Floor Displacement': 'PFD',
    # Component response
    'Peak Link Rotation Angle': 'LR',
    'Peak Link Beam Chord Rotation': 'LBR',
    # Wind Intensity
    'Peak Gust Wind Speed': 'PWS',
    # Inundation Intensity
    'Peak Inundation Height': 'PIH',
    # Shaking Intensity
    'Peak Ground Acceleration': 'PGA',
    'Peak Ground Velocity': 'PGV',
    'Spectral Acceleration': 'SA',
    'Spectral Velocity': 'SV',
    'Spectral Displacement': 'SD',
    'Peak Spectral Acceleration': 'SA',
    'Peak Spectral Velocity': 'SV',
    'Peak Spectral Displacement': 'SD',
    'Permanent Ground Deformation': 'PGD',
    # Placeholder for advanced calculations
    'One': 'ONE',
}


def dict_raise_on_duplicates(ordered_pairs: list[tuple]) -> dict:
    """
    Constructs a dictionary from a list of key-value pairs, raising an
    exception if duplicate keys are found.

    This function ensures that no two pairs have the same key. It is
    particularly useful when parsing JSON-like data where unique keys
    are expected but not enforced by standard parsing methods.

    Parameters
    ----------
    ordered_pairs : list of tuples
        A list of tuples, each containing a key and a value. Keys are
        expected to be unique across the list.

    Returns
    -------
    dict
        A dictionary constructed from the ordered_pairs without any
        duplicates.

    Raises
    ------
    ValueError
        If a duplicate key is found in the input list, a ValueError is
        raised with a message indicating the duplicate key.

    Examples
    --------
    >>> dict_raise_on_duplicates(
    ...     [("key1", "value1"), ("key2", "value2"), ("key1", "value3")]
    ... )
    ValueError: duplicate key: key1

    Notes
    -----
    This implementation is useful for contexts in which data integrity
    is crucial and key uniqueness must be ensured.
    """

    d = {}
    for k, v in ordered_pairs:
        if k in d:
            raise ValueError(f"duplicate key: {k}")
        d[k] = v
    return d


def parse_units(
    custom_file: str | None = None, preserve_categories: bool = False
) -> dict:
    """
    Parse the unit conversion factor JSON file and return a dictionary.

    Parameters
    ----------
    custom_file: str, optional
        If a custom file is provided, only the units specified in the
        custom file are used.

    Returns
    -------
    dict
        A dictionary where keys are unit names and values are
        their corresponding conversion factors. If
        `preserve_categories` is True, the dictionary may maintain
        its original nested structure based on the JSON file. If
        `preserve_categories` is False, the dictionary is flattened
        to have globally unique unit names.

    Raises
    ------
    KeyError
        If a key is defined twice.
    ValueError
        If a unit conversion factor is not a float.
    FileNotFoundError
        If a file does not exist.
    Exception
        If a file does not have the JSON format.
    """

    def get_contents(file_path, preserve_categories=False):
        """
        Parses a unit conversion factors JSON file and returns a
        dictionary mapping unit names to conversion factors.

        This function allows the use of a custom JSON file for
        defining unit conversion factors or defaults to a predefined
        file. It ensures that each unit name is unique and that all
        conversion factors are float values. Additionally, it supports
        the option to preserve the original data types of category
        values from the JSON.

        Parameters
        ----------
        file_path : str
            The file path to a JSON file containing unit conversion
            factors. If not provided, a default file is used.
        preserve_categories : bool, optional
            If True, maintains the original data types of category
            values from the JSON file. If False, converts all values
            to floats and flattens the dictionary structure, ensuring
            that each unit name is globally unique across categories.

        Returns
        -------
        dict
            A dictionary where keys are unit names and values are
            their corresponding conversion factors. If
            `preserve_categories` is True, the dictionary may maintain
            its original nested structure based on the JSON file.

        Raises
        ------
        FileNotFoundError
            If the specified file does not exist.
        ValueError
            If a unit name is duplicated, a conversion factor is not a
            float, or other JSON structure issues are present.
        json.decoder.JSONDecodeError
            If the file is not a valid JSON file.
        TypeError
            If any value that needs to be converted to float cannot be
            converted.

        Examples
        --------
        >>> parse_units('custom_units.json')
        { 'm': 1.0, 'cm': 0.01, 'mm': 0.001 }

        >>> parse_units('custom_units.json', preserve_categories=True)
        { 'Length': {'m': 1.0, 'cm': 0.01, 'mm': 0.001} }
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                dictionary = json.load(f, object_pairs_hook=dict_raise_on_duplicates)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f'{file_path} was not found.') from exc
        except json.decoder.JSONDecodeError as exc:
            raise ValueError(f'{file_path} is not a valid JSON file.') from exc
        for category_dict in list(dictionary.values()):
            # ensure all first-level keys point to a dictionary
            if not isinstance(category_dict, dict):
                raise ValueError(
                    f'{file_path} contains first-level keys '
                    'that don\'t point to a dictionary'
                )
            # convert values to float
            for key, val in category_dict.items():
                try:
                    category_dict[key] = float(val)
                except (ValueError, TypeError) as exc:
                    raise type(exc)(
                        f'Unit {key} has a value of {val} '
                        'which cannot be interpreted as a float'
                    ) from exc

        if preserve_categories:
            return dictionary

        flattened = {}
        for category in dictionary:
            for unit_name, factor in dictionary[category].items():
                if unit_name in flattened:
                    raise ValueError(f'{unit_name} defined twice in {file_path}.')
                flattened[unit_name] = factor

        return flattened

    if custom_file:
        return get_contents(custom_file, preserve_categories)

    return get_contents(
        pelicun_path / "settings/default_units.json", preserve_categories
    )


def convert_units(
    values: float | list[float] | np.ndarray,
    unit: str,
    to_unit: str,
    category: str | None = None,
) -> float | list[float] | np.ndarray:
    """
    Converts numeric values between different units.

    Supports conversion within a specified category of units and
    automatically infers the category if not explicitly provided. It
    maintains the type of the input in the output.

    Parameters
    ----------
    values (float | list[float] | np.ndarray):
      The numeric value(s) to convert.
    unit (str):
      The current unit of the values.
    to_unit (str):
      The target unit to convert the values into.
    category (Optional[str]):
      The category of the units (e.g., 'length', 'pressure'). If not
      provided, the category will be inferred based on the provided
      units.

    Returns
    -------
    float or list[float] or np.ndarray
      The converted value(s) in the target unit, in the same data type
      as the input values.

    Raises
    ------
    TypeError
      If the input `values` are not of type float, list, or
      np.ndarray.
    ValueError
      If the `unit`, `to_unit`, or `category` is unknown or if `unit`
      and `to_unit` are not in the same category.

    """

    if isinstance(values, (float, list)):
        vals = np.atleast_1d(values)
    elif isinstance(values, np.ndarray):
        vals = values
    else:
        raise TypeError('Invalid input type for `values`')

    # load default units
    all_units = parse_units(preserve_categories=True)

    # if a category is given use it, otherwise try to determine it
    if category:
        if category not in all_units:
            raise ValueError(f'Unknown category: `{category}`')
        units = all_units[category]
        for unt in unit, to_unit:
            if unt not in units:
                raise ValueError(f'Unknown unit: `{unt}`')
    else:
        unit_category: str | None = None
        for key in all_units:
            units = all_units[key]
            if unit in units:
                unit_category = key
                break
        if not unit_category:
            raise ValueError(f'Unknown unit `{unit}`')
        units = all_units[unit_category]
        if to_unit not in units:
            raise ValueError(
                f'`{unit}` is a `{unit_category}` unit, but `{to_unit}` '
                f'is not specified in that category.'
            )

    # convert units
    from_factor = units[unit]
    to_factor = units[to_unit]
    new_values = vals * float(from_factor) / float(to_factor)

    # return the results in the same type as that of the provided
    # values
    if isinstance(values, float):
        return new_values[0]
    if isinstance(values, list):
        return new_values.tolist()
    return new_values


def stringterpolation(
    arguments: str,
) -> Callable[[np.ndarray], np.ndarray]:
    """
    Turns a string of specially formatted arguments into a multilinear
    interpolating function.

    Parameters
    ----------
    arguments: str
        String of arguments containing Y values and X values,
        separated by a pipe symbol (`|`). Individual values are
        separated by commas (`,`). Example:
        arguments = 'y1,y2,y3|x1,x2,x3'

    Returns
    -------
    Callable
        A callable interpolating function

    """
    split = arguments.split('|')
    x_vals = split[1].split(',')
    y_vals = split[0].split(',')
    x = np.array(x_vals, dtype=float)
    y = np.array(y_vals, dtype=float)

    return interp1d(x=x, y=y, kind='linear')


def invert_mapping(original_dict: dict) -> dict:
    """
    Inverts a dictionary mapping from key to list of values.

    Parameters
    ----------
    original_dict : dict
        Dictionary with values that are lists of hashable items.

    Returns
    -------
    dict
        New dictionary where each item in the original value lists
        becomes a key and the original key becomes the corresponding
        value.

    Raises
    ------
    ValueError
        If any value in the original dictionary's value lists appears
        more than once.

    """
    inverted_dict = {}
    for key, value_list in original_dict.items():
        for value in value_list:
            if value in inverted_dict:
                raise ValueError('Cannot invert mapping with duplicate values.')
            inverted_dict[value] = key
    return inverted_dict
