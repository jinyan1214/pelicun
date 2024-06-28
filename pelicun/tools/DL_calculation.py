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

"""
This module provides the main functionality to run a pelicun
calculation from the command line.

"""

from __future__ import annotations
from typing import Any
from time import gmtime
from time import strftime
import sys
import os
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import colorama
from colorama import Fore
from colorama import Style

import pelicun
from pelicun.auto import auto_populate
from pelicun.base import str2bool
from pelicun.base import convert_to_MultiIndex
from pelicun.base import convert_to_SimpleIndex
from pelicun.base import describe
from pelicun.base import EDP_to_demand_type
from pelicun.file_io import load_data
from pelicun.assessment import Assessment


# pylint: disable=consider-using-namedtuple-or-dataclass
# pylint: disable=too-many-statements
# pylint: disable=too-many-nested-blocks
# pylint: disable=too-many-arguments
# pylint: disable=else-if-used
# pylint: disable=unused-argument

# pd.set_option('display.max_rows', None)

colorama.init()


def get(d: dict[str, Any], path: str, default: Any | None = None) -> Any:
    """
    Retrieve a value from a nested dictionary using a path with '/' as
    the separator.

    Parameters
    ----------
    d : dict
        The dictionary to search.
    path : str
        The path to the desired value, with keys separated by '/'.
    default : Any, optional
        The value to return if the path is not found. Defaults to
        None.

    Returns
    -------
    Any
        The value found at the specified path, or the default value if
        the path is not found.

    Examples
    --------
    >>> config = {
    ...     "DL": {
    ...         "Outputs": {
    ...             "Format": {
    ...                 "JSON": "desired_value"
    ...             }
    ...         }
    ...     }
    ... }
    >>> get(config, '/DL/Outputs/Format/JSON', default='default_value')
    'desired_value'
    >>> get(config, '/DL/Outputs/Format/XML', default='default_value')
    'default_value'

    """
    keys = path.strip('/').split('/')
    current_dict = d
    try:
        for key in keys:
            current_dict = current_dict[key]
        return current_dict
    except (KeyError, TypeError):
        return default


def update(
    d: dict[str, Any], path: str, value: Any, only_if_empty_or_none: bool = False
) -> None:
    """
    Set a value in a nested dictionary using a path with '/' as the separator.

    Parameters
    ----------
    d : dict
        The dictionary to update.
    path : str
        The path to the desired value, with keys separated by '/'.
    value : Any
        The value to set at the specified path.
    only_if_empty_or_none : bool, optional
        If True, only update the value if it is None or an empty
        dictionary. Defaults to False.

    Examples
    --------
    >>> d = {}
    >>> update(d, 'x/y/z', 1)
    >>> d
    {'x': {'y': {'z': 1}}}

    >>> update(d, 'x/y/z', 2, only_if_empty_or_none=True)
    >>> d
    {'x': {'y': {'z': 1}}}  # value remains 1 since it is not empty or None

    >>> update(d, 'x/y/z', 2)
    >>> d
    {'x': {'y': {'z': 2}}}  # value is updated to 2
    """

    keys = path.strip('/').split('/')
    current_dict = d
    for key in keys[:-1]:
        if key not in current_dict or not isinstance(current_dict[key], dict):
            current_dict[key] = {}
        current_dict = current_dict[key]
    if only_if_empty_or_none:
        if is_unspecified(current_dict, keys[-1]):
            current_dict[keys[-1]] = value
    else:
        current_dict[keys[-1]] = value


def is_unspecified(d: dict[str, Any], path: str) -> bool:
    """
    Check if a value in a nested dictionary is either non-existent,
    None, NaN, or an empty dictionary or list.

    Parameters
    ----------
    d : dict
        The dictionary to search.
    path : str
        The path to the desired value, with keys separated by '/'.

    Returns
    -------
    bool
        True if the value is non-existent, None, or an empty
        dictionary or list. False otherwise.

    Examples
    --------
    >>> config = {
    ...     "DL": {
    ...         "Outputs": {
    ...             "Format": {
    ...                 "JSON": "desired_value",
    ...                 "EmptyDict": {}
    ...             }
    ...         }
    ...     }
    ... }
    >>> is_none_or_empty(config, '/DL/Outputs/Format/JSON')
    False
    >>> is_none_or_empty(config, '/DL/Outputs/Format/XML')
    True
    >>> is_none_or_empty(config, '/DL/Outputs/Format/EmptyDict')
    True

    """
    value = get(d, path, default=None)
    if value is None:
        return True
    if pd.isna(value):
        return True
    if value == {}:
        return True
    if value == []:
        return True
    return False


def log_msg(msg):
    """
    Prints a formatted string to stdout in the form of a log. Includes
    a timestamp.

    Parameters
    ----------
    msg: str
        The message to be printed.

    """
    formatted_msg = f'{strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())} {msg}'

    print(formatted_msg)


sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

idx = pd.IndexSlice

# TODO: separate Damage Processes for
#       HAZUS Earthquake - Buildings and - Transportation
# TODO: Loss map for HAZUS EQ Transportation

damage_processes = {
    'FEMA P-58': {
        "1_excessive.coll.DEM": {"DS1": "collapse_DS1"},
        "2_collapse": {"DS1": "ALL_NA"},
        "3_excessiveRID": {"DS1": "irreparable_DS1"},
    },
    # TODO: expand with ground failure logic
    'Hazus Earthquake': {
        "1_STR": {"DS5": "collapse_DS1"},
        "2_LF": {"DS5": "collapse_DS1"},
        "3_excessive.coll.DEM": {"DS1": "collapse_DS1"},
        "4_collapse": {"DS1": "ALL_NA"},
        "5_excessiveRID": {"DS1": "irreparable_DS1"},
    },
    'Hazus Hurricane': {},
}

default_DBs = {
    'fragility': {
        'FEMA P-58': 'damage_DB_FEMA_P58_2nd.csv',
        'Hazus Earthquake - Buildings': 'damage_DB_Hazus_EQ_bldg.csv',
        'Hazus Earthquake - Stories': 'damage_DB_Hazus_EQ_story.csv',
        'Hazus Earthquake - Transportation': 'damage_DB_Hazus_EQ_trnsp.csv',
        'Hazus Earthquake - Water': 'damage_DB_Hazus_EQ_water.csv',
        'Hazus Hurricane': 'damage_DB_SimCenter_Hazus_HU_bldg.csv',
    },
    'repair': {
        'FEMA P-58': 'loss_repair_DB_FEMA_P58_2nd.csv',
        'Hazus Earthquake - Buildings': 'loss_repair_DB_Hazus_EQ_bldg.csv',
        'Hazus Earthquake - Stories': 'loss_repair_DB_Hazus_EQ_story.csv',
        'Hazus Earthquake - Transportation': 'loss_repair_DB_Hazus_EQ_trnsp.csv',
        'Hazus Hurricane': 'loss_repair_DB_SimCenter_Hazus_HU_bldg.csv',
    },
}

# list of output files help perform safe initialization of output dir
output_files = [
    "DEM_sample.zip",
    "DEM_stats.csv",
    "CMP_sample.zip",
    "CMP_stats.csv",
    "DMG_sample.zip",
    "DMG_stats.csv",
    "DMG_grp.zip",
    "DMG_grp_stats.csv",
    "DV_repair_sample.zip",
    "DV_repair_stats.csv",
    "DV_repair_grp.zip",
    "DV_repair_grp_stats.csv",
    "DV_repair_agg.zip",
    "DV_repair_agg_stats.csv",
    "DL_summary.csv",
    "DL_summary_stats.csv",
]

full_out_config = {
    'Demand': {'Sample': True, 'Statistics': True},
    'Asset': {'Sample': True, 'Statistics': True},
    'Damage': {
        'Sample': True,
        'Statistics': True,
        'GroupedSample': True,
        'GroupedStatistics': True,
    },
    'Loss': {
        'Repair': {
            'Sample': True,
            'Statistics': True,
            'GroupedSample': True,
            'GroupedStatistics': True,
            'AggregateSample': True,
            'AggregateStatistics': True,
        }
    },
    'Format': {'CSV': True, 'JSON': True},
}

regional_out_config = {
    'Demand': {'Sample': True, 'Statistics': False},
    'Asset': {'Sample': True, 'Statistics': False},
    'Damage': {
        'Sample': False,
        'Statistics': False,
        'GroupedSample': True,
        'GroupedStatistics': True,
    },
    'Loss': {
        'Repair': {
            'Sample': True,
            'Statistics': True,
            'GroupedSample': True,
            'GroupedStatistics': False,
            'AggregateSample': True,
            'AggregateStatistics': True,
        }
    },
    'Format': {'CSV': False, 'JSON': True},
    'Settings': {
        'CondenseDS': True,
        'SimpleIndexInJSON': True,
        'AggregateColocatedComponentResults': True,
    },
}

pbe_settings = {
    'CondenseDS': False,
    'SimpleIndexInJSON': False,
    'AggregateColocatedComponentResults': True,
}


def convert_df_to_dict(df, axis=1):
    """
    Convert a pandas DataFrame to a dictionary.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame to be converted.
    axis : int, optional
        The axis to consider for the conversion.
        * If 1 (default), the DataFrame is used as-is.
        * If 0, the DataFrame is transposed before conversion.

    Returns
    -------
    dict
        A dictionary representation of the DataFrame. The structure of
        the dictionary depends on the levels in the DataFrame's
        MultiIndex columns.

    Raises
    ------
    ValueError
        If the axis is not 0 or 1.

    Notes
    -----
    * If the columns have multiple levels, the function will
      recursively convert sub-DataFrames.
    * If the column labels at any level are numeric, they will be
      converted to a list of floats.
    * If the column labels are non-numeric, a dictionary will be
      created with the index labels as keys and the corresponding data
      as values.

    """

    out_dict = {}

    if axis == 1:
        df_in = df
    elif axis == 0:
        df_in = df.T
    else:
        raise ValueError('`axis` must be `0` or `1`')

    MI = df_in.columns

    for label in MI.unique(level=0):
        out_dict.update({label: np.nan})

        sub_df = df_in[label]

        skip_sub = True

        if MI.nlevels > 1:
            skip_sub = False

            if isinstance(sub_df, pd.Series):
                skip_sub = True
            elif (len(sub_df.columns) == 1) and (sub_df.columns[0] == ""):
                skip_sub = True

            if not skip_sub:
                out_dict[label] = convert_df_to_dict(sub_df)

        if skip_sub:
            if np.all(sub_df.index.astype(str).str.isnumeric()):
                out_dict_label = df_in[label].astype(float)
                out_dict[label] = out_dict_label.tolist()
            else:
                out_dict[label] = {key: sub_df.loc[key] for key in sub_df.index}

    return out_dict


def add_units(raw_demands, length_unit):
    """
    Add units to demand columns in a DataFrame.

    Parameters
    ----------
    raw_demands : pd.DataFrame
        The raw demand data to which units will be added.
    length_unit : str
        The unit of length to be used (e.g., 'in' for inches).

    Returns
    -------
    pd.DataFrame
        The DataFrame with units added to the appropriate demand columns.

    """
    demands = raw_demands.T

    demands.insert(0, "Units", np.nan)

    if length_unit == 'in':
        length_unit = 'inch'

    demands = convert_to_MultiIndex(demands, axis=0).sort_index(axis=0).T

    if demands.columns.nlevels == 4:
        DEM_level = 1
    else:
        DEM_level = 0

    # drop demands with no EDP type identified
    demands.drop(
        demands.columns[demands.columns.get_level_values(DEM_level) == ''],
        axis=1,
        inplace=True,
    )

    # assign units
    demand_cols = demands.columns.get_level_values(DEM_level)

    # remove additional info from demand names
    demand_cols = [d.split('_')[0] for d in demand_cols]

    # acceleration
    acc_EDPs = ['PFA', 'PGA', 'SA']
    EDP_mask = np.isin(demand_cols, acc_EDPs)

    if np.any(EDP_mask):
        demands.iloc[0, EDP_mask] = length_unit + 'ps2'

    # speed
    speed_EDPs = ['PFV', 'PWS', 'PGV', 'SV']
    EDP_mask = np.isin(demand_cols, speed_EDPs)

    if np.any(EDP_mask):
        demands.iloc[0, EDP_mask] = length_unit + 'ps'

    # displacement
    disp_EDPs = ['PFD', 'PIH', 'SD', 'PGD']
    EDP_mask = np.isin(demand_cols, disp_EDPs)

    if np.any(EDP_mask):
        demands.iloc[0, EDP_mask] = length_unit

    # drift ratio
    rot_EDPs = ['PID', 'PRD', 'DWD', 'RDR', 'PMD', 'RID']
    EDP_mask = np.isin(demand_cols, rot_EDPs)

    if np.any(EDP_mask):
        demands.iloc[0, EDP_mask] = 'unitless'

    # convert back to simple header and return the DF
    return convert_to_SimpleIndex(demands, axis=1)


def run_pelicun(
    config_path,
    demand_file,
    output_path,
    coupled_EDP,
    realizations,
    auto_script_path,
    detailed_results,
    regional,
    output_format,
    custom_model_dir,
    color_warnings,
    **kwargs,
):
    """
    Use settings in the config JSON to prepare and run a Pelicun calculation.

    Parameters
    ----------
    config_path: string
        Path pointing to the location of the JSON configuration file.
    demand_file: string
        Path pointing to the location of a CSV file with the demand data.
    output_path: string, optional
        Path pointing to the location where results shall be saved.
    coupled_EDP: bool, optional
        If True, EDPs are not resampled and processed in order.
    realizations: int, optional
        Number of realizations to generate.
    auto_script_path: string, optional
        Path pointing to the location of a Python script with an auto_populate
        method that automatically creates the performance model using data
        provided in the AIM JSON file.
    detailed_results: bool, optional
        If False, only the main statistics are saved.
    regional: bool
        Currently unused.
    output_format: str
        Type of output format, JSON or CSV.
    custom_model_dir: string, optional
        Path pointing to a directory with files that define user-provided model
        parameters for a customized damage and loss assessment.
    color_warnings: bool, optional
        If True, warnings are printed in red on the console. If output
        is redirected to a file, it will contain ANSI codes. When
        viewed on the console with `cat`, `less`, or similar utilites,
        the color will be shown.

    Returns
    -------
    bool
       0 if the calculation was ran successfully, or -1 otherwise.

    """

    log_msg('First line of DL_calculation')

    # Initial setup -----------------------------------------------------------

    # color warnings
    cpref, csuff = _get_color_codes(color_warnings)

    # get the absolute path to the config file
    config_path = Path(config_path).resolve()

    # If the output path was not specified, results are saved in the directory
    # of the input file.
    if output_path is None:
        output_path = config_path.parents[0]
    else:
        output_path = Path(output_path)

    # Initialize the array that we'll use to collect the output file names
    out_files = _remove_existing_files(output_path)

    # open the config file and parse it
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # f"{config['commonFileDir']}/CustomDLModels/"
    custom_dl_file_path = custom_model_dir

    if is_unspecified(config, 'DL'):
        log_msg("Damage and Loss configuration missing from config file. ")

        if auto_script_path is not None:
            log_msg("Trying to auto-populate")

            config_ap, CMP = auto_populate(config, auto_script_path)

            if is_unspecified(config_ap, 'DL'):

                log_msg(
                    "The prescribed auto-population script failed to identify "
                    "a valid damage and loss configuration for this asset. "
                    "Terminating analysis."
                )

                return -1

            # add the demand information
            update(config_ap, '/DL/Demands/DemandFilePath', demand_file)
            update(config_ap, '/DL/Demands/SampleSize', str(realizations))

            if coupled_EDP is True:
                update(config_ap, 'DL/Demands/CoupledDemands', True)

            else:
                update(
                    config_ap,
                    'DL/Demands/Calibration',
                    {"ALL": {"DistributionFamily": "lognormal"}},
                )

            # save the component data
            CMP.to_csv(output_path / 'CMP_QNT.csv')

            # update the config file with the location
            update(
                config_ap,
                'DL/Asset/ComponentAssignmentFile',
                str(output_path / 'CMP_QNT.csv'),
            )

            # if detailed results are not requested, add a lean output config
            if detailed_results is False:
                update(config_ap, 'DL/Outputs', regional_out_config)
            else:
                update(config_ap, 'DL/Outputs', full_out_config)
                # add output settings from regional output config
                if is_unspecified(config_ap, 'DL/Outputs/Settings'):
                    update(config_ap, 'DL/Outputs/Settings', {})

                config_ap['DL']['Outputs']['Settings'].update(
                    regional_out_config['Settings']
                )

            # save the extended config to a file
            config_ap_path = Path(config_path.stem + '_ap.json').resolve()

            with open(config_ap_path, 'w', encoding='utf-8') as f:
                json.dump(config_ap, f, indent=2)

            update(config, 'DL', get(config_ap, 'DL'))

        else:
            log_msg("Terminating analysis.")

            return -1

    #
    # sample size: backwards compatibility
    #
    sample_size_str = (
        # expected location
        get(config, 'Options/Sampling/SampleSize')
    )
    if not sample_size_str:
        # try previous location
        sample_size_str = get(config, 'DL/Demands/SampleSize')
    if not sample_size_str:
        # give up
        print('Sample size not provided in config file. Terminating analysis.')
        return -1
    sample_size = int(sample_size_str)

    # provide all outputs if the files are not specified
    if is_unspecified(config, 'DL/Outputs'):
        update(config, 'DL/Outputs', full_out_config)

    # provide outputs in CSV by default
    if is_unspecified(config, 'DL/Outputs/Format'):
        update(config, 'DL/Outputs/Format', {'CSV': True, 'JSON': False})

    # override file format specification if the output_format is provided
    if output_format is not None:
        update(
            config,
            'DL/Outputs/Format',
            {
                'CSV': 'csv' in output_format,
                'JSON': 'json' in output_format,
            },
        )

    # add empty Settings to output config to simplify code below
    if is_unspecified(config, 'DL/Outputs/Settings'):
        update(config, 'DL/Outputs/Settings', pbe_settings)

    if is_unspecified(config, 'DL/Asset'):
        log_msg("Asset configuration missing. Terminating analysis.")
        return -1

    if is_unspecified(config, 'DL/Demands'):
        log_msg("Demand configuration missing. Terminating analysis.")
        return -1

    # get the length unit from the config file
    try:
        length_unit = get(config, 'GeneralInformation/units/length')
    except KeyError:
        log_msg(
            "No default length unit provided in the input file. "
            "Terminating analysis. "
        )
        return -1

    # initialize the Pelicun Assessement
    update(config, 'DL/Options/LogFile', 'pelicun_log.txt')
    update(config, 'DL/Options/Verbose', True)

    # If the user did not prescribe anything for ListAllDamageStates,
    # then use True as default for DL_calculations regardless of what
    # the Pelicun default is.
    update(
        config, 'DL/Options/ListAllDamageStates', True, only_if_empty_or_none=True
    )

    PAL = Assessment(get(config, 'DL/Options'))

    # Demand Assessment -----------------------------------------------------------

    # check if there is a demand file location specified in the config file
    _demand(config, config_path, length_unit, PAL, sample_size)

    # if requested, save results
    if not is_unspecified(config, 'DL/Outputs/Demand'):
        demand_sample = _demand_save(config, PAL, output_path, out_files)
    else:
        demand_sample, _ = PAL.demand.save_sample(save_units=True)

    # Asset Definition ------------------------------------------------------------

    # set the number of stories
    cmp_marginals = _asset(config, PAL, demand_sample, cpref, csuff)

    # if requested, save results
    if get(config, 'DL/Outputs/Asset', default=False):
        _asset_save(PAL, config, output_path, out_files)

    # Damage Assessment -----------------------------------------------------------

    # if a damage assessment is requested
    if not is_unspecified(config, 'DL/Damage'):
        # load the fragility information
        try:

            _damage(config, custom_dl_file_path, PAL, cmp_marginals, length_unit)

            # if requested, save results
            if not is_unspecified(config, 'DL/Outputs/Damage'):
                damage_sample = _damage_save(PAL, config, output_path, out_files)
            else:
                damage_sample, _ = PAL.damage.save_sample(save_units=True)

        except ValueError:
            return -1
    else:
        damage_sample, _ = PAL.damage.save_sample(save_units=True)

    # Loss Assessment -----------------------------------------------------------

    # if a loss assessment is requested
    if not is_unspecified(config, 'DL/Losses'):
        try:
            agg_repair = _loss(
                config, PAL, custom_dl_file_path, output_path, out_files
            )
        except ValueError as e:
            print(f'Exception occurred: {str(e)}. Terminating analysis')
            return -1
    else:
        agg_repair = None

    # Result Summary -----------------------------------------------------------

    _summary(PAL, agg_repair, damage_sample, config, output_path, out_files)

    return 0


def _damage_save(PAL, config, output_path, out_files):
    damage_sample, damage_units = PAL.damage.save_sample(save_units=True)
    damage_units = damage_units.to_frame().T

    if (
        get(
            config,
            'DL/Outputs/Settings/AggregateColocatedComponentResults',
            default=False,
        )
        is True
    ):
        damage_units = damage_units.groupby(level=[0, 1, 2, 4], axis=1).first()

        damage_groupby_uid = damage_sample.groupby(level=[0, 1, 2, 4], axis=1)

        damage_sample = damage_groupby_uid.sum().mask(
            damage_groupby_uid.count() == 0, np.nan
        )

    out_reqs = [
        out if val else "" for out, val in get(config, 'DL/Outputs/Damage').items()
    ]

    if np.any(
        np.isin(
            [
                'Sample',
                'Statistics',
                'GroupedSample',
                'GroupedStatistics',
            ],
            out_reqs,
        )
    ):
        if 'Sample' in out_reqs:
            damage_sample_s = pd.concat([damage_sample, damage_units])

            damage_sample_s = convert_to_SimpleIndex(damage_sample_s, axis=1)
            damage_sample_s.to_csv(
                output_path / "DMG_sample.zip",
                index_label=damage_sample_s.columns.name,
                compression={
                    'method': 'zip',
                    'archive_name': 'DMG_sample.csv',
                },
            )
            out_files.append('DMG_sample.zip')

        if 'Statistics' in out_reqs:
            damage_stats = describe(damage_sample)
            damage_stats = pd.concat([damage_stats, damage_units])

            damage_stats = convert_to_SimpleIndex(damage_stats, axis=1)
            damage_stats.to_csv(
                output_path / "DMG_stats.csv",
                index_label=damage_stats.columns.name,
            )
            out_files.append('DMG_stats.csv')

        if np.any(np.isin(['GroupedSample', 'GroupedStatistics'], out_reqs)):
            if (
                get(
                    config,
                    'DL/Outputs/Settings/AggregateColocatedComponentResults',
                    default=False,
                )
                is True
            ):
                damage_groupby = damage_sample.groupby(level=[0, 1, 3], axis=1)

                damage_units = damage_units.groupby(level=[0, 1, 3], axis=1).first()

            else:
                damage_groupby = damage_sample.groupby(level=[0, 1, 4], axis=1)

                damage_units = damage_units.groupby(level=[0, 1, 4], axis=1).first()

            grp_damage = damage_groupby.sum().mask(
                damage_groupby.count() == 0, np.nan
            )

            # if requested, condense DS output
            if (
                get(
                    config,
                    'DL/Outputs/Settings/CondenseDS',
                    default=False,
                )
                is True
            ):
                # replace non-zero values with 1
                grp_damage = grp_damage.mask(
                    grp_damage.astype(np.float64).values > 0, 1
                )

                # get the corresponding DS for each column
                ds_list = grp_damage.columns.get_level_values(2).astype(int)

                # replace ones with the corresponding DS in each cell
                grp_damage = grp_damage.mul(ds_list, axis=1)

                # aggregate across damage state indices
                damage_groupby_2 = grp_damage.groupby(level=[0, 1], axis=1)

                # choose the max value
                # i.e., the governing DS for each comp-loc pair
                grp_damage = damage_groupby_2.max().mask(
                    damage_groupby_2.count() == 0, np.nan
                )

                # aggregate units to the same format
                # assume identical units across locations for each comp
                damage_units = damage_units.groupby(level=[0, 1], axis=1).first()

            else:
                # otherwise, aggregate damage quantities for each comp
                damage_groupby_2 = grp_damage.groupby(level=0, axis=1)

                # preserve NaNs
                grp_damage = damage_groupby_2.sum().mask(
                    damage_groupby_2.count() == 0, np.nan
                )

                # and aggregate units to the same format
                damage_units = damage_units.groupby(level=0, axis=1).first()

            if 'GroupedSample' in out_reqs:
                grp_damage_s = pd.concat([grp_damage, damage_units])

                grp_damage_s = convert_to_SimpleIndex(grp_damage_s, axis=1)
                grp_damage_s.to_csv(
                    output_path / "DMG_grp.zip",
                    index_label=grp_damage_s.columns.name,
                    compression={
                        'method': 'zip',
                        'archive_name': 'DMG_grp.csv',
                    },
                )
                out_files.append('DMG_grp.zip')

            if 'GroupedStatistics' in out_reqs:
                grp_stats = describe(grp_damage)
                grp_stats = pd.concat([grp_stats, damage_units])

                grp_stats = convert_to_SimpleIndex(grp_stats, axis=1)
                grp_stats.to_csv(
                    output_path / "DMG_grp_stats.csv",
                    index_label=grp_stats.columns.name,
                )
                out_files.append('DMG_grp_stats.csv')
    return damage_sample


def _asset_save(PAL, config, output_path, out_files):
    cmp_sample, cmp_units = PAL.asset.save_cmp_sample(save_units=True)
    cmp_units = cmp_units.to_frame().T

    if (
        get(
            config,
            'DL/Outputs/Settings/AggregateColocatedComponentResults',
            default=False,
        )
        is True
    ):
        cmp_units = cmp_units.groupby(level=[0, 1, 2], axis=1).first()

        cmp_groupby_uid = cmp_sample.groupby(level=[0, 1, 2], axis=1)

        cmp_sample = cmp_groupby_uid.sum().mask(cmp_groupby_uid.count() == 0, np.nan)

    out_reqs = [
        out if val else "" for out, val in get(config, 'DL/Outputs/Asset').items()
    ]

    if np.any(np.isin(['Sample', 'Statistics'], out_reqs)):
        if 'Sample' in out_reqs:
            cmp_sample_s = pd.concat([cmp_sample, cmp_units])

            cmp_sample_s = convert_to_SimpleIndex(cmp_sample_s, axis=1)
            cmp_sample_s.to_csv(
                output_path / "CMP_sample.zip",
                index_label=cmp_sample_s.columns.name,
                compression={'method': 'zip', 'archive_name': 'CMP_sample.csv'},
            )
            out_files.append('CMP_sample.zip')

        if 'Statistics' in out_reqs:
            cmp_stats = describe(cmp_sample)
            cmp_stats = pd.concat([cmp_stats, cmp_units])

            cmp_stats = convert_to_SimpleIndex(cmp_stats, axis=1)
            cmp_stats.to_csv(
                output_path / "CMP_stats.csv", index_label=cmp_stats.columns.name
            )
            out_files.append('CMP_stats.csv')


def _demand_save(config, PAL, output_path, out_files):
    out_reqs = [
        out if val else "" for out, val in get(config, 'DL/Outputs/Demand').items()
    ]

    if np.any(np.isin(['Sample', 'Statistics'], out_reqs)):
        demand_sample, demand_units = PAL.demand.save_sample(save_units=True)

        demand_units = demand_units.to_frame().T

        if 'Sample' in out_reqs:
            demand_sample_s = pd.concat([demand_sample, demand_units])
            demand_sample_s = convert_to_SimpleIndex(demand_sample_s, axis=1)
            demand_sample_s.to_csv(
                output_path / "DEM_sample.zip",
                index_label=demand_sample_s.columns.name,
                compression={'method': 'zip', 'archive_name': 'DEM_sample.csv'},
            )
            out_files.append('DEM_sample.zip')

        if 'Statistics' in out_reqs:
            demand_stats = describe(demand_sample)
            demand_stats = pd.concat([demand_stats, demand_units])
            demand_stats = convert_to_SimpleIndex(demand_stats, axis=1)
            demand_stats.to_csv(
                output_path / "DEM_stats.csv",
                index_label=demand_stats.columns.name,
            )
            out_files.append('DEM_stats.csv')
    return demand_sample


def _remove_existing_files(output_path):
    # Initialize the array that we'll use to collect the output file names
    out_files = []

    # Initialize the output folder - i.e., remove existing output files from
    # there
    files = os.listdir(output_path)
    for filename in files:
        if filename in out_files:
            os.remove(output_path / filename)
    return out_files


def _summary(PAL, agg_repair, damage_sample, config, output_path, out_files):
    damage_sample = damage_sample.groupby(level=[0, 3], axis=1).sum()
    damage_sample_s = convert_to_SimpleIndex(damage_sample, axis=1)

    if 'collapse-1' in damage_sample_s.columns:
        damage_sample_s['collapse'] = damage_sample_s['collapse-1']
    else:
        damage_sample_s['collapse'] = np.zeros(damage_sample_s.shape[0])

    if 'irreparable-1' in damage_sample_s.columns:
        damage_sample_s['irreparable'] = damage_sample_s['irreparable-1']
    else:
        damage_sample_s['irreparable'] = np.zeros(damage_sample_s.shape[0])

    if agg_repair is not None:
        agg_repair_s = convert_to_SimpleIndex(agg_repair, axis=1)

    else:
        agg_repair_s = pd.DataFrame()

    summary = pd.concat(
        [agg_repair_s, damage_sample_s[['collapse', 'irreparable']]], axis=1
    )

    summary_stats = describe(summary)

    # save summary sample
    summary.to_csv(output_path / "DL_summary.csv", index_label='#')
    out_files.append('DL_summary.csv')

    # save summary statistics
    summary_stats.to_csv(output_path / "DL_summary_stats.csv")
    out_files.append('DL_summary_stats.csv')

    # create json outputs if needed
    if get(config, 'DL/Outputs/Format/JSON') is True:
        for filename in out_files:
            filename_json = filename[:-3] + 'json'

            if (
                get(config, 'DL/Outputs/Settings/SimpleIndexInJSON', default=False)
                is True
            ):
                df = pd.read_csv(output_path / filename, index_col=0)
            else:
                df = convert_to_MultiIndex(
                    pd.read_csv(output_path / filename, index_col=0), axis=1
                )

            if "Units" in df.index:
                df_units = convert_to_SimpleIndex(
                    df.loc['Units', :].to_frame().T, axis=1
                )

                df.drop("Units", axis=0, inplace=True)

                out_dict = convert_df_to_dict(df)

                out_dict.update(
                    {
                        "Units": {
                            col: df_units.loc["Units", col]
                            for col in df_units.columns
                        }
                    }
                )

            else:
                out_dict = convert_df_to_dict(df)

            with open(output_path / filename_json, 'w', encoding='utf-8') as f:
                json.dump(out_dict, f, indent=2)

    # remove csv outputs if they were not requested
    if get(config, 'DL/Outputs/Format/CSV', default=False) is False:
        for filename in out_files:
            # keep the DL_summary and DL_summary_stats files
            if 'DL_summary' in filename:
                continue
            os.remove(output_path / filename)


def _demand(config, config_path, length_unit, PAL, sample_size):
    # check if there is a demand file location specified in the config file
    if get(config, 'DL/Demands/DemandFilePath', default=False):
        demand_path = Path(get(config, 'DL/Demands/DemandFilePath')).resolve()

    else:
        # otherwise assume that there is a response.csv file next to the config file
        demand_path = config_path.parent / 'response.csv'

    # try to load the demands
    raw_demands = pd.read_csv(demand_path, index_col=0)

    # remove excessive demands that are considered collapses, if needed
    if get(config, 'DL/Demands/CollapseLimits', default=False):
        raw_demands = convert_to_MultiIndex(raw_demands, axis=1)

        if 'Units' in raw_demands.index:
            raw_units = raw_demands.loc['Units', :]
            raw_demands.drop('Units', axis=0, inplace=True)

        else:
            raw_units = None

        DEM_to_drop = np.full(raw_demands.shape[0], False)

        for DEM_type, limit in get(config, 'DL/Demands/CollapseLimits').items():
            if raw_demands.columns.nlevels == 4:
                DEM_to_drop += raw_demands.loc[:, idx[:, DEM_type, :, :]].max(
                    axis=1
                ) > float(limit)

            else:
                DEM_to_drop += raw_demands.loc[:, idx[DEM_type, :, :]].max(
                    axis=1
                ) > float(limit)

        raw_demands = raw_demands.loc[~DEM_to_drop, :]

        if isinstance(raw_units, pd.Series):
            raw_demands = pd.concat([raw_demands, raw_units.to_frame().T], axis=0)

        log_msg(
            f"{np.sum(DEM_to_drop)} realizations removed from the demand "
            f"input because they exceed the collapse limit. The remaining "
            f"sample size: {raw_demands.shape[0]}"
        )

    # add units to the demand data if needed
    if "Units" not in raw_demands.index:
        demands = add_units(raw_demands, length_unit)

    else:
        demands = raw_demands

    # load the available demand sample
    PAL.demand.load_sample(demands)

    # get the calibration information
    if get(config, 'DL/Demands/Calibration', default=False):
        # then use it to calibrate the demand model
        PAL.demand.calibrate_model(get(config, 'DL/Demands/Calibration'))

    else:
        # if no calibration is requested,
        # set all demands to use empirical distribution
        PAL.demand.calibrate_model({"ALL": {"DistributionFamily": "empirical"}})

    # and generate a new demand sample
    PAL.demand.generate_sample(
        {
            "SampleSize": sample_size,
            'PreserveRawOrder': get(
                config, 'DL/Demands/CoupledDemands', default=False
            ),
            'DemandCloning': get(config, 'DL/Demands/DemandCloning', default=False),
        }
    )

    # get the generated demand sample
    demand_sample, demand_units = PAL.demand.save_sample(save_units=True)

    demand_sample = pd.concat([demand_sample, demand_units.to_frame().T])

    # get residual drift estimates, if needed
    if get(config, 'DL/Demands/InferResidualDrift', default=False):
        if get(config, 'DL/Demands/InferResidualDrift/method') == 'FEMA P-58':
            RID_list = []
            PID = demand_sample['PID'].copy()
            PID.drop('Units', inplace=True)
            PID = PID.astype(float)

            for direction, delta_yield in get(
                config, 'DL/Demands/InferResidualDrift'
            ).items():
                if direction == 'method':
                    continue

                RID = PAL.demand.estimate_RID(
                    PID.loc[:, idx[:, direction]],
                    {'yield_drift': float(delta_yield)},
                )

                RID_list.append(RID)

            RID = pd.concat(RID_list, axis=1)
            RID_units = pd.Series(
                ['unitless'] * RID.shape[1],
                index=RID.columns,
                name='Units',
            )
            RID_sample = pd.concat([RID, RID_units.to_frame().T])
            demand_sample = pd.concat([demand_sample, RID_sample], axis=1)

    # add a constant one demand
    demand_sample[('ONE', '0', '1')] = np.ones(demand_sample.shape[0])
    demand_sample.loc['Units', ('ONE', '0', '1')] = 'unitless'

    PAL.demand.load_sample(convert_to_SimpleIndex(demand_sample, axis=1))


def _asset(config, PAL, demand_sample, cpref, csuff):
    # set the number of stories
    if get(config, 'DL/Asset/NumberOfStories', default=False):
        PAL.stories = int(get(config, 'DL/Asset/NumberOfStories'))

    # load a component model and generate a sample
    if get(config, 'DL/Asset/ComponentAssignmentFile', default=False):
        cmp_marginals = pd.read_csv(
            get(config, 'DL/Asset/ComponentAssignmentFile'),
            index_col=0,
            encoding_errors='replace',
        )

        DEM_types = demand_sample.columns.unique(level=0)

        # add component(s) to support collapse calculation
        if get(config, 'DL/Damage/CollapseFragility', default=False):
            coll_DEM = get(config, 'DL/Damage/CollapseFragility/DemandType')
            if not coll_DEM.startswith('SA'):
                # we need story-specific collapse assessment
                # (otherwise we have a global demand and evaluate
                # collapse directly, so this code should be skipped)

                if coll_DEM in DEM_types:
                    # excessive coll_DEM is added on every floor to detect large RIDs
                    cmp_marginals.loc['excessive.coll.DEM', 'Units'] = 'ea'

                    locs = demand_sample[coll_DEM].columns.unique(level=0)
                    cmp_marginals.loc['excessive.coll.DEM', 'Location'] = ','.join(
                        locs
                    )

                    dirs = demand_sample[coll_DEM].columns.unique(level=1)
                    cmp_marginals.loc['excessive.coll.DEM', 'Direction'] = ','.join(
                        dirs
                    )

                    cmp_marginals.loc['excessive.coll.DEM', 'Theta_0'] = 1.0

                else:
                    log_msg(
                        f'{cpref}WARNING: No {coll_DEM} among available '
                        f'demands. Collapse '
                        f'cannot be evaluated.{csuff}'
                    )

        # always add a component to support basic collapse calculation
        cmp_marginals.loc['collapse', 'Units'] = 'ea'
        cmp_marginals.loc['collapse', 'Location'] = 0
        cmp_marginals.loc['collapse', 'Direction'] = 1
        cmp_marginals.loc['collapse', 'Theta_0'] = 1.0

        # add components to support irreparable damage calculation
        if not is_unspecified(config, 'DL/Damage/IrreparableDamage'):
            if 'RID' in DEM_types:
                # excessive RID is added on every floor to detect large RIDs
                cmp_marginals.loc['excessiveRID', 'Units'] = 'ea'

                locs = demand_sample['RID'].columns.unique(level=0)
                cmp_marginals.loc['excessiveRID', 'Location'] = ','.join(locs)

                dirs = demand_sample['RID'].columns.unique(level=1)
                cmp_marginals.loc['excessiveRID', 'Direction'] = ','.join(dirs)

                cmp_marginals.loc['excessiveRID', 'Theta_0'] = 1.0

                # irreparable is a global component to recognize is any of the
                # excessive RIDs were triggered
                cmp_marginals.loc['irreparable', 'Units'] = 'ea'
                cmp_marginals.loc['irreparable', 'Location'] = 0
                cmp_marginals.loc['irreparable', 'Direction'] = 1
                cmp_marginals.loc['irreparable', 'Theta_0'] = 1.0

            else:
                log_msg(
                    f'{cpref}WARNING: No residual interstory drift ratio among'
                    f'available demands. Irreparable damage cannot be '
                    f'evaluated.{csuff}'
                )

        # load component model
        PAL.asset.load_cmp_model({'marginals': cmp_marginals})

        # generate component quantity sample
        PAL.asset.generate_cmp_sample()

    # if requested, load the quantity sample from a file
    elif get(config, 'DL/Asset/ComponentSampleFile', default=False):
        PAL.asset.load_cmp_sample(get(config, 'DL/Asset/ComponentSampleFile'))
    return cmp_marginals


def _damage(config, custom_dl_file_path, PAL, cmp_marginals, length_unit):
    if get(config, 'DL/Asset/ComponentDatabase') in default_DBs['fragility']:
        component_db = [
            'PelicunDefault/'
            + default_DBs['fragility'][get(config, 'DL/Asset/ComponentDatabase')],
        ]
    else:
        component_db = []

    if get(config, 'DL/Asset/ComponentDatabasePath', default=False) is not False:
        extra_comps = get(config, 'DL/Asset/ComponentDatabasePath')

        if 'CustomDLDataFolder' in extra_comps:
            extra_comps = extra_comps.replace(
                'CustomDLDataFolder', custom_dl_file_path
            )

        component_db += [
            extra_comps,
        ]
    component_db = component_db[::-1]

    # prepare additional fragility data

    # get the database header from the default P58 db
    P58_data = PAL.get_default_data('damage_DB_FEMA_P58_2nd')

    adf = pd.DataFrame(columns=P58_data.columns)

    if not is_unspecified(config, 'DL/Damage/CollapseFragility'):
        if 'excessive.coll.DEM' in cmp_marginals.index:
            # if there is story-specific evaluation
            coll_CMP_name = 'excessive.coll.DEM'
        else:
            # otherwise, for global collapse evaluation
            coll_CMP_name = 'collapse'

        adf.loc[coll_CMP_name, ('Demand', 'Directional')] = 1
        adf.loc[coll_CMP_name, ('Demand', 'Offset')] = 0

        coll_DEM = get(config, 'DL/Damage/CollapseFragility/DemandType')

        if '_' in coll_DEM:
            coll_DEM, coll_DEM_spec = coll_DEM.split('_')
        else:
            coll_DEM_spec = None

        coll_DEM_name = None
        for demand_name, demand_short in EDP_to_demand_type.items():
            if demand_short == coll_DEM:
                coll_DEM_name = demand_name
                break

        if coll_DEM_name is None:
            raise ValueError('`coll_DEM_name` cannot be None.')

        if coll_DEM_spec is None:
            adf.loc[coll_CMP_name, ('Demand', 'Type')] = coll_DEM_name

        else:
            adf.loc[coll_CMP_name, ('Demand', 'Type')] = (
                f'{coll_DEM_name}|{coll_DEM_spec}'
            )

        coll_DEM_unit = add_units(
            pd.DataFrame(
                columns=[
                    f'{coll_DEM}-1-1',
                ]
            ),
            length_unit,
        ).iloc[0, 0]

        adf.loc[coll_CMP_name, ('Demand', 'Unit')] = coll_DEM_unit

        adf.loc[coll_CMP_name, ('LS1', 'Family')] = get(
            config,
            'DL/Damage/CollapseFragility/CapacityDistribution',
            default=np.nan,
        )

        adf.loc[coll_CMP_name, ('LS1', 'Theta_0')] = get(
            config, 'DL/Damage/CollapseFragility/CapacityMedian', default=np.nan
        )

        adf.loc[coll_CMP_name, ('LS1', 'Theta_1')] = get(
            config, 'DL/Damage/CollapseFragility/Theta_1', default=np.nan
        )

        adf.loc[coll_CMP_name, 'Incomplete'] = 0

        if coll_CMP_name != 'collapse':
            # for story-specific evaluation, we need to add a placeholder
            # fragility that will never trigger, but helps us aggregate
            # results in the end
            adf.loc['collapse', ('Demand', 'Directional')] = 1
            adf.loc['collapse', ('Demand', 'Offset')] = 0
            adf.loc['collapse', ('Demand', 'Type')] = 'One'
            adf.loc['collapse', ('Demand', 'Unit')] = 'unitless'
            adf.loc['collapse', ('LS1', 'Theta_0')] = 1e10
            adf.loc['collapse', 'Incomplete'] = 0

    elif is_unspecified(config, 'DL/Asset/ComponentDatabase/Water'):
        # add a placeholder collapse fragility that will never trigger
        # collapse, but allow damage processes to work with collapse

        adf.loc['collapse', ('Demand', 'Directional')] = 1
        adf.loc['collapse', ('Demand', 'Offset')] = 0
        adf.loc['collapse', ('Demand', 'Type')] = 'One'
        adf.loc['collapse', ('Demand', 'Unit')] = 'unitless'
        adf.loc['collapse', ('LS1', 'Theta_0')] = 1e10
        adf.loc['collapse', 'Incomplete'] = 0

    if not is_unspecified(config, 'DL/Damage/IrreparableDamage'):

        # add excessive RID fragility according to settings provided in the
        # input file
        adf.loc['excessiveRID', ('Demand', 'Directional')] = 1
        adf.loc['excessiveRID', ('Demand', 'Offset')] = 0
        adf.loc['excessiveRID', ('Demand', 'Type')] = (
            'Residual Interstory Drift Ratio'
        )

        adf.loc['excessiveRID', ('Demand', 'Unit')] = 'unitless'
        adf.loc['excessiveRID', ('LS1', 'Theta_0')] = get(
            config, 'DL/Damage/IrreparableDamage/DriftCapacityMedian'
        )

        adf.loc['excessiveRID', ('LS1', 'Family')] = "lognormal"

        adf.loc['excessiveRID', ('LS1', 'Theta_1')] = get(
            config, 'DL/Damage/IrreparableDamage/DriftCapacityLogStd'
        )

        adf.loc['excessiveRID', 'Incomplete'] = 0

        # add a placeholder irreparable fragility that will never trigger
        # damage, but allow damage processes to aggregate excessiveRID here
        adf.loc['irreparable', ('Demand', 'Directional')] = 1
        adf.loc['irreparable', ('Demand', 'Offset')] = 0
        adf.loc['irreparable', ('Demand', 'Type')] = 'One'
        adf.loc['irreparable', ('Demand', 'Unit')] = 'unitless'
        adf.loc['irreparable', ('LS1', 'Theta_0')] = 1e10
        adf.loc['irreparable', 'Incomplete'] = 0

    # TODO: we can improve this by creating a water
    # network-specific assessment class
    if not is_unspecified(config, 'DL/Asset/ComponentDatabase/Water'):
        # add a placeholder aggregate fragility that will never trigger
        # damage, but allow damage processes to aggregate the
        # various pipeline damages
        adf.loc['aggregate', ('Demand', 'Directional')] = 1
        adf.loc['aggregate', ('Demand', 'Offset')] = 0
        adf.loc['aggregate', ('Demand', 'Type')] = 'Peak Ground Velocity'
        adf.loc['aggregate', ('Demand', 'Unit')] = 'mps'
        adf.loc['aggregate', ('LS1', 'Theta_0')] = 1e10
        adf.loc['aggregate', ('LS2', 'Theta_0')] = 1e10
        adf.loc['aggregate', 'Incomplete'] = 0

    PAL.damage.load_damage_model(component_db + [adf])

    # load the damage process if needed
    dmg_process = None
    if get(config, 'DL/Damage/DamageProcess', default=False) is not False:
        dp_approach = get(config, 'DL/Damage/DamageProcess')

        if dp_approach in damage_processes:
            dmg_process = damage_processes[dp_approach]

            # For Hazus Earthquake, we need to specify the component ids
            if dp_approach == 'Hazus Earthquake':
                cmp_sample = PAL.asset.save_cmp_sample()

                cmp_list = cmp_sample.columns.unique(level=0)

                cmp_map = {'STR': '', 'LF': '', 'NSA': ''}

                for cmp in cmp_list:
                    for cmp_type in cmp_map:
                        if cmp_type + '.' in cmp:
                            cmp_map[cmp_type] = cmp

                new_dmg_process = dmg_process.copy()
                for source_cmp, action in dmg_process.items():
                    # first, look at the source component id
                    new_source = None
                    for cmp_type, cmp_id in cmp_map.items():
                        if (cmp_type in source_cmp) and (cmp_id != ''):
                            new_source = source_cmp.replace(cmp_type, cmp_id)
                            break

                    if new_source is not None:
                        new_dmg_process[new_source] = action
                        del new_dmg_process[source_cmp]
                    else:
                        new_source = source_cmp

                    # then, look at the target component ids
                    for ds_i, target_vals in action.items():
                        if isinstance(target_vals, str):
                            for cmp_type, cmp_id in cmp_map.items():
                                if (cmp_type in target_vals) and (cmp_id != ''):
                                    target_vals = target_vals.replace(
                                        cmp_type, cmp_id
                                    )

                            new_target_vals = target_vals

                        else:
                            # we assume that target_vals is a list of str
                            new_target_vals = []

                            for target_val in target_vals:
                                for cmp_type, cmp_id in cmp_map.items():
                                    if (cmp_type in target_val) and (cmp_id != ''):
                                        target_val = target_val.replace(
                                            cmp_type, cmp_id
                                        )

                                new_target_vals.append(target_val)

                        new_dmg_process[new_source][ds_i] = new_target_vals

                dmg_process = new_dmg_process

        elif dp_approach == "User Defined":
            # load the damage process from a file
            with open(
                get(config, 'DL/Damage/DamageProcessFilePath'),
                'r',
                encoding='utf-8',
            ) as f:
                dmg_process = json.load(f)

        elif dp_approach == "None":
            # no damage process applied for the calculation
            dmg_process = None

        else:
            log_msg(f"Prescribed Damage Process not recognized: " f"{dp_approach}")

    # calculate damages
    PAL.damage.calculate(dmg_process=dmg_process)


def _loss(config, PAL, custom_dl_file_path, output_path, out_files):
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # backwards-compatibility for v3.2 and earlier | remove after v4.0
    if get(config, 'DL/Losses/BldgRepair', default=False):
        update(config, 'DL/Losses/Repair', get(config, 'DL/Losses/BldgRepair'))

    if get(config, 'DL/Outputs/Loss/BldgRepair', default=False):
        update(
            config,
            'DL/Outputs/Loss/Repair',
            get(config, 'DL/Outputs/Loss/BldgRepair'),
        )
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    # if requested, calculate repair consequences
    if get(config, 'DL/Losses/Repair', default=False):

        # load the fragility information
        conseq_df, consequence_db = _load_fragility_info(
            config, PAL, custom_dl_file_path
        )

        # remove duplicates from conseq_df
        conseq_df = conseq_df.loc[conseq_df.index.unique(), :]

        # add the replacement consequence to the data
        adf = pd.DataFrame(
            columns=conseq_df.columns,
            index=pd.MultiIndex.from_tuples(
                [
                    ('replacement', 'Cost'),
                    ('replacement', 'Time'),
                    ('replacement', 'Carbon'),
                    ('replacement', 'Energy'),
                ]
            ),
        )

        # DL_method = get(config, 'DL/Losses/Repair')['ConsequenceDatabase']
        DL_method = get(config, 'DL/Damage/DamageProcess', default='User Defined')

        _loss__cost(config, adf, DL_method)

        _loss__time(config, adf, DL_method, conseq_df)

        _loss__carbon(config, adf, DL_method)

        _loss__energy(config, adf, DL_method)

        # prepare the loss map
        loss_map = None
        if get(config, 'DL/Losses/Repair/MapApproach') == "Automatic":
            # get the damage sample
            loss_map = _loss__map_auto(PAL, conseq_df, DL_method, config)

        elif get(config, 'DL/Losses/Repair/MapApproach') == "User Defined":
            loss_map = _loss__map_user(custom_dl_file_path, config)

        # prepare additional loss map entries, if needed
        if 'DMG-collapse' not in loss_map.index:
            loss_map.loc['DMG-collapse', 'Repair'] = 'replacement'
            loss_map.loc['DMG-irreparable', 'Repair'] = 'replacement'

        # assemble the list of requested decision variables
        DV_list = []
        if (
            get(config, 'DL/Losses/Repair/DecisionVariables', default=False)
            is not False
        ):
            for DV_i, DV_status in get(
                config, 'DL/Losses/Repair/DecisionVariables'
            ).items():
                if DV_status is True:
                    DV_list.append(DV_i)

        else:
            DV_list = None

        PAL.repair.load_model(
            consequence_db + [adf],
            loss_map,
            decision_variables=DV_list,
        )

        PAL.repair.calculate()

        agg_repair = PAL.repair.aggregate_losses()

        # if requested, save results
        if get(config, 'DL/Outputs/Loss/Repair', default=False):
            _loss_save(PAL, config, output_path, out_files, agg_repair)

        return agg_repair
    return None


def _load_fragility_info(config, PAL, custom_dl_file_path):
    if get(config, 'DL/Losses/Repair/ConsequenceDatabase') in default_DBs['repair']:
        consequence_db = [
            'PelicunDefault/'
            + default_DBs['repair'][
                get(config, 'DL/Losses/Repair/ConsequenceDatabase')
            ],
        ]

        conseq_df = PAL.get_default_data(
            default_DBs['repair'][
                get(config, 'DL/Losses/Repair/ConsequenceDatabase')
            ][:-4]
        )
    else:
        consequence_db = []

        conseq_df = pd.DataFrame()

    if (
        get(config, 'DL/Losses/Repair/ConsequenceDatabasePath', default=False)
        is not False
    ):
        extra_comps = get(config, 'DL/Losses/Repair/ConsequenceDatabasePath')

        if 'CustomDLDataFolder' in extra_comps:
            extra_comps = extra_comps.replace(
                'CustomDLDataFolder', custom_dl_file_path
            )

        consequence_db += [extra_comps]

        extra_conseq_df = load_data(
            extra_comps,
            unit_conversion_factors=None,
            orientation=1,
            reindex=False,
        )

        if isinstance(conseq_df, pd.DataFrame):
            conseq_df = pd.concat([conseq_df, extra_conseq_df])
        else:
            conseq_df = extra_conseq_df

    consequence_db = consequence_db[::-1]
    return conseq_df, consequence_db


def _loss_save(PAL, config, output_path, out_files, agg_repair):
    repair_sample, repair_units = PAL.repair.save_sample(save_units=True)
    repair_units = repair_units.to_frame().T

    if (
        get(
            config,
            'DL/Outputs/Settings/AggregateColocatedComponentResults',
            default=False,
        )
        is True
    ):
        repair_units = repair_units.groupby(level=[0, 1, 2, 3, 4, 5], axis=1).first()

        repair_groupby_uid = repair_sample.groupby(level=[0, 1, 2, 3, 4, 5], axis=1)

        repair_sample = repair_groupby_uid.sum().mask(
            repair_groupby_uid.count() == 0, np.nan
        )

    out_reqs = [
        out if val else ""
        for out, val in get(config, 'DL/Outputs/Loss/Repair').items()
    ]

    if np.any(
        np.isin(
            [
                'Sample',
                'Statistics',
                'GroupedSample',
                'GroupedStatistics',
                'AggregateSample',
                'AggregateStatistics',
            ],
            out_reqs,
        )
    ):
        if 'Sample' in out_reqs:
            repair_sample_s = repair_sample.copy()
            repair_sample_s = pd.concat([repair_sample_s, repair_units])

            repair_sample_s = convert_to_SimpleIndex(repair_sample_s, axis=1)
            repair_sample_s.to_csv(
                output_path / "DV_repair_sample.zip",
                index_label=repair_sample_s.columns.name,
                compression={
                    'method': 'zip',
                    'archive_name': 'DV_repair_sample.csv',
                },
            )
            out_files.append('DV_repair_sample.zip')

        if 'Statistics' in out_reqs:
            repair_stats = describe(repair_sample)
            repair_stats = pd.concat([repair_stats, repair_units])

            repair_stats = convert_to_SimpleIndex(repair_stats, axis=1)
            repair_stats.to_csv(
                output_path / "DV_repair_stats.csv",
                index_label=repair_stats.columns.name,
            )
            out_files.append('DV_repair_stats.csv')

        if np.any(np.isin(['GroupedSample', 'GroupedStatistics'], out_reqs)):
            repair_groupby = repair_sample.groupby(level=[0, 1, 2], axis=1)

            repair_units = repair_units.groupby(level=[0, 1, 2], axis=1).first()

            grp_repair = repair_groupby.sum().mask(
                repair_groupby.count() == 0, np.nan
            )

            if 'GroupedSample' in out_reqs:
                grp_repair_s = pd.concat([grp_repair, repair_units])

                grp_repair_s = convert_to_SimpleIndex(grp_repair_s, axis=1)
                grp_repair_s.to_csv(
                    output_path / "DV_repair_grp.zip",
                    index_label=grp_repair_s.columns.name,
                    compression={
                        'method': 'zip',
                        'archive_name': 'DV_repair_grp.csv',
                    },
                )
                out_files.append('DV_repair_grp.zip')

            if 'GroupedStatistics' in out_reqs:
                grp_stats = describe(grp_repair)
                grp_stats = pd.concat([grp_stats, repair_units])

                grp_stats = convert_to_SimpleIndex(grp_stats, axis=1)
                grp_stats.to_csv(
                    output_path / "DV_repair_grp_stats.csv",
                    index_label=grp_stats.columns.name,
                )
                out_files.append('DV_repair_grp_stats.csv')

        if np.any(np.isin(['AggregateSample', 'AggregateStatistics'], out_reqs)):
            if 'AggregateSample' in out_reqs:
                agg_repair_s = convert_to_SimpleIndex(agg_repair, axis=1)
                agg_repair_s.to_csv(
                    output_path / "DV_repair_agg.zip",
                    index_label=agg_repair_s.columns.name,
                    compression={
                        'method': 'zip',
                        'archive_name': 'DV_repair_agg.csv',
                    },
                )
                out_files.append('DV_repair_agg.zip')

            if 'AggregateStatistics' in out_reqs:
                agg_stats = convert_to_SimpleIndex(describe(agg_repair), axis=1)
                agg_stats.to_csv(
                    output_path / "DV_repair_agg_stats.csv",
                    index_label=agg_stats.columns.name,
                )
                out_files.append('DV_repair_agg_stats.csv')


def _loss__map_user(custom_dl_file_path, config):
    if get(config, 'DL/Losses/Repair/MapFilePath', default=False) is not False:
        loss_map_path = get(config, 'DL/Losses/Repair/MapFilePath')

        loss_map_path = loss_map_path.replace(
            'CustomDLDataFolder', custom_dl_file_path
        )

    else:
        raise ValueError('Missing loss map path.')

    loss_map = pd.read_csv(loss_map_path, index_col=0)
    return loss_map


def _loss__map_auto(PAL, conseq_df, DL_method, config):
    # get the damage sample
    dmg_sample = PAL.damage.save_sample()

    # create a mapping for all components that are also in
    # the prescribed consequence database
    dmg_cmps = dmg_sample.columns.unique(level='cmp')
    loss_cmps = conseq_df.index.unique(level=0)

    drivers = []
    loss_models = []

    if DL_method in {'FEMA P-58', 'Hazus Hurricane'}:
        # with these methods, we assume fragility and consequence data
        # have the same IDs

        for dmg_cmp in dmg_cmps:
            if dmg_cmp == 'collapse':
                continue

            if dmg_cmp in loss_cmps:
                drivers.append(f'DMG-{dmg_cmp}')
                loss_models.append(dmg_cmp)

    elif DL_method in {
        'Hazus Earthquake',
        'Hazus Earthquake Transportation',
    }:
        # with Hazus Earthquake we assume that consequence
        # archetypes are only differentiated by occupancy type
        occ_type = get(config, 'DL/Asset/OccupancyType', default=None)

        for dmg_cmp in dmg_cmps:
            if dmg_cmp == 'collapse':
                continue

            cmp_class = dmg_cmp.split('.')[0]
            if occ_type is not None:
                loss_cmp = f'{cmp_class}.{occ_type}'
            else:
                loss_cmp = cmp_class

            if loss_cmp in loss_cmps:
                drivers.append(f'DMG-{dmg_cmp}')
                loss_models.append(loss_cmp)

    loss_map = pd.DataFrame(loss_models, columns=['Repair'], index=drivers)
    return loss_map


def _loss__energy(config, adf, DL_method):
    ren = ('replacement', 'Energy')
    if 'ReplacementEnergy' in get(config, 'DL/Losses/Repair'):
        ren = ('replacement', 'Energy')

        adf.loc[ren, ('Quantity', 'Unit')] = "1 EA"

        adf.loc[ren, ('DV', 'Unit')] = get(
            config, 'DL/Losses/Repair/ReplacementEnergy/Unit'
        )

        adf.loc[ren, ('DS1', 'Theta_0')] = get(
            config, 'DL/Losses/Repair/ReplacementEnergy/Median'
        )

        if (
            pd.isna(get(config, 'DL/Losses/Repair/ReplacementEnergy/Distribution'))
            is False
        ):
            adf.loc[ren, ('DS1', 'Family')] = get(
                config, 'DL/Losses/Repair/ReplacementEnergy/Distribution'
            )
            adf.loc[ren, ('DS1', 'Theta_1')] = get(
                config, 'DL/Losses/Repair/ReplacementEnergy/Theta_1'
            )
    else:
        # add a default replacement energy value as a placeholder
        # the default value depends on the consequence database

        # for FEMA P-58, use 0 kg
        if DL_method == 'FEMA P-58':
            adf.loc[ren, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[ren, ('DV', 'Unit')] = 'MJ'
            adf.loc[ren, ('DS1', 'Theta_0')] = 0

        else:
            # for everything else, remove this consequence
            adf.drop(ren, inplace=True)


def _loss__carbon(config, adf, DL_method):
    rcarb = ('replacement', 'Carbon')
    if not is_unspecified(config, 'DL/Losses/Repair/ReplacementCarbon'):

        rcarb = ('replacement', 'Carbon')

        adf.loc[rcarb, ('Quantity', 'Unit')] = "1 EA"

        adf.loc[rcarb, ('DV', 'Unit')] = get(
            config, 'DL/Losses/Repair/ReplacementCarbon/Unit'
        )

        adf.loc[rcarb, ('DS1', 'Theta_0')] = get(
            config, 'DL/Losses/Repair/ReplacementCarbon/Median'
        )

        if (
            pd.isna(get(config, 'DL/Losses/Repair/ReplacementCarbon/Distribution'))
            is False
        ):
            adf.loc[rcarb, ('DS1', 'Family')] = get(
                config, 'DL/Losses/Repair/ReplacementCarbon/Distribution'
            )
            adf.loc[rcarb, ('DS1', 'Theta_1')] = get(
                config, 'DL/Losses/Repair/ReplacementCarbon/Theta_1'
            )
    else:
        # add a default replacement carbon value as a placeholder
        # the default value depends on the consequence database

        # for FEMA P-58, use 0 kg
        if DL_method == 'FEMA P-58':
            adf.loc[rcarb, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rcarb, ('DV', 'Unit')] = 'kg'
            adf.loc[rcarb, ('DS1', 'Theta_0')] = 0

        else:
            # for everything else, remove this consequence
            adf.drop(rcarb, inplace=True)


def _loss__time(config, adf, DL_method, conseq_df):
    rt = ('replacement', 'Time')
    if not is_unspecified(config, 'DL/Losses/Repair/ReplacementTime'):
        rt = ('replacement', 'Time')

        adf.loc[rt, ('Quantity', 'Unit')] = "1 EA"

        adf.loc[rt, ('DV', 'Unit')] = get(
            config, 'DL/Losses/Repair/ReplacementTime/Unit'
        )

        adf.loc[rt, ('DS1', 'Theta_0')] = get(
            config, 'DL/Losses/Repair/ReplacementTime/Median'
        )

        if (
            pd.isna(
                get(
                    config,
                    'DL/Losses/Repair/ReplacementTime/Distribution',
                    default=np.nan,
                )
            )
            is False
        ):
            adf.loc[rt, ('DS1', 'Family')] = get(
                config, 'DL/Losses/Repair/ReplacementTime/Distribution'
            )
            adf.loc[rt, ('DS1', 'Theta_1')] = get(
                config, 'DL/Losses/Repair/ReplacementTime/Theta_1'
            )
    else:
        # add a default replacement time value as a placeholder
        # the default value depends on the consequence database

        # for FEMA P-58, use 0 worker_days
        if DL_method == 'FEMA P-58':
            adf.loc[rt, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rt, ('DV', 'Unit')] = 'worker_day'
            adf.loc[rt, ('DS1', 'Theta_0')] = 0

        # for Hazus EQ, use 1.0 as a loss_ratio
        elif DL_method == 'Hazus Earthquake - Buildings':
            adf.loc[rt, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rt, ('DV', 'Unit')] = 'day'

            # load the replacement time that corresponds to total loss
            occ_type = config['DL']['Asset']['OccupancyType']
            adf.loc[rt, ('DS1', 'Theta_0')] = conseq_df.loc[
                (f"STR.{occ_type}", 'Time'), ('DS5', 'Theta_0')
            ]

        # otherwise, use 1 (and expect to have it defined by the user)
        else:
            adf.loc[rt, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rt, ('DV', 'Unit')] = 'loss_ratio'
            adf.loc[rt, ('DS1', 'Theta_0')] = 1


def _loss__cost(config, adf, DL_method):
    rc = ('replacement', 'Cost')
    if not is_unspecified(config, 'DL/Losses/Repair/ReplacementCost'):

        adf.loc[rc, ('Quantity', 'Unit')] = "1 EA"

        adf.loc[rc, ('DV', 'Unit')] = get(
            config, 'DL/Losses/Repair/ReplacementCost/Unit'
        )

        adf.loc[rc, ('DS1', 'Theta_0')] = get(
            config, 'DL/Losses/Repair/ReplacementCost/Median'
        )

        if (
            pd.isna(
                get(
                    config,
                    'DL/Losses/Repair/ReplacementCost/Distribution',
                    default=np.nan,
                )
            )
            is False
        ):
            adf.loc[rc, ('DS1', 'Family')] = get(
                config, 'DL/Losses/Repair/ReplacementCost/Distribution'
            )
            adf.loc[rc, ('DS1', 'Theta_1')] = get(
                config, 'DL/Losses/Repair/ReplacementCost/Theta_1'
            )

    else:
        # add a default replacement cost value as a placeholder
        # the default value depends on the consequence database

        # for FEMA P-58, use 0 USD
        if DL_method == 'FEMA P-58':
            adf.loc[rc, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rc, ('DV', 'Unit')] = 'USD_2011'
            adf.loc[rc, ('DS1', 'Theta_0')] = 0

        # for Hazus EQ and HU, use 1.0 as a loss_ratio
        elif DL_method in {'Hazus Earthquake', 'Hazus Hurricane'}:
            adf.loc[rc, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rc, ('DV', 'Unit')] = 'loss_ratio'

            # store the replacement cost that corresponds to total loss
            adf.loc[rc, ('DS1', 'Theta_0')] = 1.00

        # otherwise, use 1 (and expect to have it defined by the user)
        else:
            adf.loc[rc, ('Quantity', 'Unit')] = '1 EA'
            adf.loc[rc, ('DV', 'Unit')] = 'loss_ratio'
            adf.loc[rc, ('DS1', 'Theta_0')] = 1


def _get_color_codes(color_warnings):
    if color_warnings:
        cpref = Fore.RED
        csuff = Style.RESET_ALL
    else:
        cpref = csuff = ''
    return cpref, csuff


def main():
    """
    Main method to parse arguments and run the pelicun calculation.

    """
    args = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--filenameDL')
    parser.add_argument('-d', '--demandFile', default=None)
    parser.add_argument('-s', '--Realizations', default=None)
    parser.add_argument('--dirnameOutput', default=None)
    parser.add_argument('--event_time', default=None)
    parser.add_argument(
        '--detailed_results', default=True, type=str2bool, nargs='?', const=True
    )
    parser.add_argument(
        '--coupled_EDP', default=False, type=str2bool, nargs='?', const=False
    )
    parser.add_argument(
        '--log_file', default=True, type=str2bool, nargs='?', const=True
    )
    parser.add_argument(
        '--ground_failure', default=False, type=str2bool, nargs='?', const=False
    )
    parser.add_argument('--auto_script', default=None)
    parser.add_argument('--resource_dir', default=None)
    parser.add_argument('--custom_model_dir', default=None)
    parser.add_argument(
        '--regional', default=False, type=str2bool, nargs='?', const=False
    )
    parser.add_argument('--output_format', default=None)
    parser.add_argument(
        '--color_warnings', default=False, type=str2bool, nargs='?', const=False
    )
    # parser.add_argument('-d', '--demandFile', default=None)
    # parser.add_argument('--DL_Method', default = None)
    # parser.add_argument('--outputBIM', default='BIM.csv')
    # parser.add_argument('--outputEDP', default='EDP.csv')
    # parser.add_argument('--outputDM', default='DM.csv')
    # parser.add_argument('--outputDV', default='DV.csv')

    if not args:
        print(f'Welcome. This is pelicun version {pelicun.__version__}')
        print(
            'To access the documentation visit '
            'https://nheri-simcenter.github.io/pelicun/index.html'
        )
        print()
        parser.print_help()
        return

    args = parser.parse_args(args)

    log_msg('Initializing pelicun calculation...')

    # print(args)
    out = run_pelicun(
        args.filenameDL,
        demand_file=args.demandFile,
        output_path=args.dirnameOutput,
        realizations=args.Realizations,
        detailed_results=args.detailed_results,
        coupled_EDP=args.coupled_EDP,
        log_file=args.log_file,
        event_time=args.event_time,
        ground_failure=args.ground_failure,
        auto_script_path=args.auto_script,
        resource_dir=args.resource_dir,
        custom_model_dir=args.custom_model_dir,
        color_warnings=args.color_warnings,
        regional=args.regional,
        output_format=args.output_format,
    )

    if out == -1:
        log_msg("pelicun calculation failed.")
    else:
        log_msg('pelicun calculation completed.')


if __name__ == '__main__':
    main()
