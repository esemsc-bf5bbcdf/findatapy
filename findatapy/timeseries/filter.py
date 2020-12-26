__author__ = 'saeedamen'  # Saeed Amen

#
# Copyright 2016-2020 Cuemacro
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# See the License for the specific language governing permissions and limitations under the License.
#



import re

import numpy as np
import pandas as pd
import pytz

import datetime
from datetime import timedelta

import pandas.tseries.offsets

from pandas.tseries.offsets import BDay, CustomBusinessDay, Day, CustomBusinessMonthEnd, DateOffset


from findatapy.timeseries.timezone import Timezone

from findatapy.util.dataconstants import DataConstants
from findatapy.util.loggermanager import LoggerManager

constants = DataConstants()

class Filter(object):
    """Functions for filtering time series by dates and columns.

    This class is used extensively in both findatapy and finmarketpy.

    Market holidays are collected from web sources such as https://www.timeanddate.com/holidays/ and also individual
    exchange websites, and is manually updated from time to time to take into account newly instituted holidays, and stored
    in conf/holidays_table.parquet - if you need to add your own holidays.

    """

    _time_series_cache = {}  # shared across all instances of object!

    def __init__(self):
        self._calendar = Calendar()

    def filter_time_series(self, market_data_request, data_frame, pad_columns=False):
        """Filters a time series given a set of criteria (like start/finish date and tickers)

        Parameters
        ----------
        market_data_request : MarketDataRequest
            defining time series filtering
        data_frame : DataFrame
            time series to be filtered
        pad_columns : boolean
            true, non-existant columns with nan

        Returns
        -------
        DataFrame
        """
        start_date = market_data_request.start_date
        finish_date = market_data_request.finish_date

        data_frame = self.filter_time_series_by_date(start_date, finish_date, data_frame)

        # filter by ticker.field combinations requested
        columns = self.create_tickers_fields_list(market_data_request)

        if (pad_columns):
            data_frame = self.pad_time_series_columns(columns, data_frame)
        else:
            data_frame = self.filter_time_series_by_columns(columns, data_frame)

        return data_frame

    def filter_time_series_by_holidays(self, data_frame, cal='FX', holidays_list=[]):
        """Removes holidays from a given time series

        Parameters
        ----------
        data_frame : DataFrame
            data frame to be filtered
        cal : str
            business calendar to use

        Returns
        -------
        DataFrame
        """

        # Optimal case for weekdays: remove Saturday and Sunday
        if (cal == 'WEEKDAY' or cal == 'WKY'):
            return data_frame[data_frame.index.dayofweek <= 4]

        # Select only those holidays in the sample
        holidays_start = self._calendar.get_holidays(data_frame.index[0], data_frame.index[-1], cal, holidays_list=holidays_list)

        if (holidays_start.size == 0):
            return data_frame

        holidays_end = holidays_start + np.timedelta64(1, 'D')

        # floored_dates = data_frame.index.normalize()
        #
        # filter_by_index_start = floored_dates.searchsorted(holidays_start)
        # filter_by_index_end = floored_dates.searchsorted(holidays_end)
        #
        # indices_to_keep = []
        #
        # if filter_by_index_end[0] == 0:
        #     counter = filter_by_index_end[0] + 1
        #     start_index = 1
        # else:
        #     counter = 0
        #     start_index = 0
        #
        # for i in range(start_index, len(holidays_start)):
        #     indices = list(range(counter, filter_by_index_start[i] - 1))
        #     indices_to_keep = indices_to_keep + indices
        #
        #     counter = filter_by_index_end[i] + 1
        #
        # indices = list(range(counter, len(floored_dates)))
        # indices_to_keep = indices_to_keep + indices
        #
        # data_frame_filtered = data_frame[indices_to_keep]

        if data_frame.index.tz is None:
            holidays_start = holidays_start.tz_localize(None)
            holidays_end = holidays_end.tz_localize(None)

        data_frame_left = data_frame
        data_frame_filtered = []

        for i in range(0, len(holidays_start)):
            data_frame_temp = data_frame_left[data_frame_left.index < holidays_start[i]]
            data_frame_left = data_frame_left[data_frame_left.index >= holidays_end[i]]

            data_frame_filtered.append(data_frame_temp)

        data_frame_filtered.append(data_frame_left)

        return pd.concat(data_frame_filtered)

    def filter_time_series_by_date(self, start_date, finish_date, data_frame):
        """Filter time series by start/finish dates

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        finish_date : DataTime
            finish date of calendar
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        offset = 0  # inclusive

        return self.filter_time_series_by_date_offset(start_date, finish_date, data_frame, offset,
                                                      exclude_start_end=False)

    def filter_time_series_by_days(self, days, data_frame):
        """Filter time series by start/finish dates

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        finish_date : DataTime
            finish date of calendar
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        offset = 0  # inclusive

        finish_date = datetime.datetime.utcnow()
        start_date = finish_date - timedelta(days=days)
        return self.filter_time_series_by_date_offset(start_date, finish_date, data_frame, offset)

    def filter_time_series_by_date_exc(self, start_date, finish_date, data_frame):
        """Filter time series by start/finish dates (exclude start & finish dates)

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        finish_date : DataTime
            finish date of calendar
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        offset = 1  # exclusive of start finish date

        return self.filter_time_series_by_date_offset(start_date, finish_date, data_frame, offset,
                                                      exclude_start_end=True)

        # try:
        #     # filter by dates for intraday data
        #     if(start_date is not None):
        #         data_frame = data_frame.loc[start_date <= data_frame.index]
        #
        #     if(finish_date is not None):
        #         # filter by start_date and finish_date
        #         data_frame = data_frame.loc[data_frame.index <= finish_date]
        # except:
        #     # filter by dates for daily data
        #     if(start_date is not None):
        #         data_frame = data_frame.loc[start_date.date() <= data_frame.index]
        #
        #     if(finish_date is not None):
        #         # filter by start_date and finish_date
        #         data_frame = data_frame.loc[data_frame.index <= finish_date.date()]
        #
        # return data_frame

    def filter_time_series_by_date_offset(self, start_date, finish_date, data_frame, offset, exclude_start_end=False):
        """Filter time series by start/finish dates (and an offset)

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        finish_date : DataTime
            finish date of calendar
        data_frame : DataFrame
            data frame to be filtered
        offset : int
            offset to be applied

        Returns
        -------
        DataFrame
        """

        if hasattr(data_frame.index, 'tz'):
            if data_frame.index.tz is not None:

                # If the start/finish dates are timezone naive, overwrite with the DataFrame timezone
                if not (isinstance(start_date, str)):
                    start_date = start_date.replace(tzinfo=data_frame.index.tz)

                if not (isinstance(finish_date, str)):
                    finish_date = finish_date.replace(tzinfo=data_frame.index.tz)
            else:
                # Otherwise remove timezone from start_date/finish_date
                if not (isinstance(start_date, str)):
                    start_date = start_date.replace(tzinfo=None)

                if not (isinstance(finish_date, str)):
                    finish_date = finish_date.replace(tzinfo=None)

        if 'int' in str(data_frame.index.dtype):
            return data_frame

        try:
            data_frame = self.filter_time_series_aux(start_date, finish_date, data_frame, offset)
        except:
            # start_date = start_date.date()
            # finish_date = finish_date.date()
            # if isinstance(start_date, str):
            #     # format expected 'Jun 1 2005 01:33', '%b %d %Y %H:%M'
            #     try:
            #         start_date = datetime.datetime.strptime(start_date, '%b %d %Y %H:%M')
            #     except:
            #         i = 0
            #
            # if isinstance(finish_date, str):
            #     # format expected 'Jun 1 2005 01:33', '%b %d %Y %H:%M'
            #     try:
            #         finish_date = datetime.datetime.strptime(finish_date, '%b %d %Y %H:%M')
            #     except:
            #         i = 0

            # try:
            #     start_date = start_date.date()
            # except: pass
            #
            # try:
            #     finish_date = finish_date.date()
            # except: pass

            # if we have dates stored as opposed to TimeStamps (ie. daily data), we use a simple (slower) method
            # for filtering daily data
            if (start_date is not None):
                if exclude_start_end:
                    data_frame = data_frame.loc[start_date < data_frame.index]
                else:
                    data_frame = data_frame.loc[start_date <= data_frame.index]

            if (finish_date is not None):
                if exclude_start_end:
                    data_frame = data_frame.loc[data_frame.index < finish_date]
                else:
                    # filter by start_date and finish_date
                    data_frame = data_frame.loc[data_frame.index <= finish_date]

        return data_frame

    def filter_time_series_aux(self, start_date, finish_date, data_frame, offset):
        """Filter time series by start/finish dates (and an offset)

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        finish_date : DataTime
            finish date of calendar
        data_frame : DataFrame
            data frame to be filtered
        offset : int (not implemented!)
            offset to be applied

        Returns
        -------
        DataFrame
        """

        # start_index = 0
        # finish_index = len(data_frame.index) - offset

        # filter by dates for intraday data
        # if(start_date is not None):
        #     start_index = data_frame.index.searchsorted(start_date)
        #
        #     if (0 <= start_index + offset < len(data_frame.index)):
        #         start_index = start_index + offset
        #
        #         # data_frame = data_frame[start_date < data_frame.index]
        #
        # if(finish_date is not None):
        #     finish_index = data_frame.index.searchsorted(finish_date)
        #
        #     if (0 <= finish_index - offset < len(data_frame.index)):
        #         finish_index = finish_index - offset
        # CAREFUL: need + 1 otherwise will only return 1 less than usual
        # return data_frame.iloc[start_date:finish_date]

        # Just use pandas, quicker and simpler code!
        if data_frame is None:
            return None

        # Slower method..
        # return data_frame.loc[start_date:finish_date]

        # Much faster, start and finish dates are inclusive
        return data_frame[(data_frame.index >= start_date) & (data_frame.index <= finish_date)]

    def filter_time_series_by_time_of_day_timezone(self, hour, minute, data_frame, timezone_of_snap='UTC'):

        old_tz = data_frame.index.tz
        data_frame = data_frame.tz_convert(pytz.timezone(timezone_of_snap))

        data_frame = data_frame[data_frame.index.minute == minute]
        data_frame = data_frame[data_frame.index.hour == hour]

        data_frame = data_frame.tz_convert(old_tz)

        return data_frame

    def filter_time_series_by_time_of_day(self, hour, minute, data_frame, in_tz=None, out_tz=None):
        """Filter time series by time of day

        Parameters
        ----------
        hour : int
            hour of day
        minute : int
            minute of day
        data_frame : DataFrame
            data frame to be filtered
        in_tz : str (optional)
            time zone of input data frame
        out_tz : str (optional)
            time zone of output data frame

        Returns
        -------
        DataFrame
        """
        if out_tz is not None:
            try:
                if in_tz is not None:
                    data_frame = data_frame.tz_localize(pytz.timezone(in_tz))
            except:
                data_frame = data_frame.tz_convert(pytz.timezone(in_tz))

            data_frame = data_frame.tz_convert(pytz.timezone(out_tz))

            # change internal representation of time
            data_frame.index = pd.DatetimeIndex(data_frame.index.values)

        data_frame = data_frame[data_frame.index.minute == minute]
        data_frame = data_frame[data_frame.index.hour == hour]

        return data_frame

    def filter_time_series_by_minute_of_hour(self, minute, data_frame, in_tz=None, out_tz=None):
        """Filter time series by minute of hour

        Parameters
        ----------
        minute : int
            minute of hour
        data_frame : DataFrame
            data frame to be filtered
        in_tz : str (optional)
            time zone of input data frame
        out_tz : str (optional)
            time zone of output data frame

        Returns
        -------
        DataFrame
        """
        if out_tz is not None:
            if in_tz is not None:
                data_frame = data_frame.tz_localize(pytz.timezone(in_tz))

            data_frame = data_frame.tz_convert(pytz.timezone(out_tz))

            # change internal representation of time
            data_frame.index = pd.DatetimeIndex(data_frame.index.values)

        data_frame = data_frame[data_frame.index.minute == minute]

        return data_frame

    def filter_time_series_between_hours(self, start_hour, finish_hour, data_frame):
        """Filter time series between hours of the day

        Parameters
        ----------
        start_hour : int
            start of hour filter
        finish_hour : int
            finish of hour filter
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """

        data_frame = data_frame[data_frame.index.hour <= finish_hour]
        data_frame = data_frame[data_frame.index.hour >= start_hour]

        return data_frame

    def filter_time_series_by_columns(self, columns, data_frame):
        """Filter time series by certain columns

        Parameters
        ----------
        columns : list(str)
            start of hour filter
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        if data_frame is not None and columns is not None:
            return data_frame[columns]

        return None

    def pad_time_series_columns(self, columns, data_frame):
        """Selects time series from a dataframe and if necessary creates empty columns

        Parameters
        ----------
        columns : str
            columns to be included with this keyword
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        old_columns = data_frame.columns

        common_columns = [val for val in columns if val in old_columns]
        uncommon_columns = [val for val in columns if val not in old_columns]
        uncommon_columns = [str(x) for x in uncommon_columns]

        data_frame = data_frame[common_columns]

        if len(uncommon_columns) > 0:
            logger = LoggerManager().getLogger(__name__)

            logger.info("Padding missing columns...")  # " + str(uncommon_columns))

            new_data_frame = pd.DataFrame(index=data_frame.index, columns=uncommon_columns)

            data_frame = pd.concat([data_frame, new_data_frame], axis=1)

            # SLOW method below
            # for x in uncommon_columns: data_frame.loc[:,x] = np.nan

        # get columns in same order again
        data_frame = data_frame[columns]

        return data_frame

    def filter_time_series_by_excluded_keyword(self, keyword, data_frame):
        """Filter time series to exclude columns which contain keyword

        Parameters
        ----------
        keyword : str
            columns to be excluded with this keyword
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """

        if not (isinstance(keyword, list)):
            keyword = [keyword]

        columns = []

        for k in keyword:
            columns.append([elem for elem in data_frame.columns if k not in elem])

        columns = self._calendar.flatten_list_of_lists(columns)

        return self.filter_time_series_by_columns(columns, data_frame)

    def filter_time_series_by_included_keyword(self, keyword, data_frame):
        """Filter time series to include columns which contain keyword

        Parameters
        ----------
        keyword : str
            columns to be included with this keyword
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """

        if not (isinstance(keyword, list)):
            keyword = [keyword]

        columns = []

        for k in keyword:
            columns.append([elem for elem in data_frame.columns if k in elem])

        columns = self._calendar.flatten_list_of_lists(columns)

        return self.filter_time_series_by_columns(columns, data_frame)

    def filter_time_series_by_minute_freq(self, freq, data_frame):
        """Filter time series where minutes correspond to certain minute filter

        Parameters
        ----------
        freq : int
            minute frequency to be filtered
        data_frame : DataFrame
            data frame to be filtered

        Returns
        -------
        DataFrame
        """
        return data_frame.loc[data_frame.index.minute % freq == 0]

    def create_tickers_fields_list(self, market_data_request):
        """Creates a list of tickers concatenated with fields from a MarketDataRequest

        Parameters
        ----------
        market_data_request : MarketDataRequest
            request to be expanded

        Returns
        -------
        list(str)
        """
        tickers = market_data_request.tickers
        fields = market_data_request.fields

        if isinstance(tickers, str): tickers = [tickers]
        if isinstance(fields, str): fields = [fields]

        tickers_fields_list = []

        # Create ticker.field combination for series we wish to return
        for f in fields:
            for t in tickers:
                tickers_fields_list.append(t + '.' + f)

        return tickers_fields_list

    def resample_time_series(self, data_frame, freq):
        return data_frame.asfreq(freq, method='pad')

    def resample_time_series_frequency(self, data_frame, data_resample_freq,
                                       data_resample_type='mean', fill_empties=False):
        # Should we take the mean, first, last in our resample
        if data_resample_type == 'mean':
            data_frame_r = data_frame.resample(data_resample_freq).mean()
        elif data_resample_type == 'first':
            data_frame_r = data_frame.resample(data_resample_freq).first()
        elif data_resample_type == 'last':
            data_frame_r = data_frame.resample(data_resample_freq).last()
        else:
            # TODO implement other types
            return

        if fill_empties == True:
            data_frame, data_frame_r = data_frame.align(data_frame_r, join='left', axis=0)
            data_frame_r = data_frame_r.fillna(method='ffill')

        return data_frame_r

    def make_FX_1_min_working_days(self, data_frame):
        data_frame = data_frame.resample('1min').mean()
        data_frame = self.filter_time_series_by_holidays(data_frame, 'FX')
        data_frame = data_frame.fillna(method='ffill')
        data_frame = self.remove_out_FX_out_of_hours(data_frame)

        return data_frame

    def remove_out_FX_out_of_hours(self, data_frame):
        """Filtered a time series for FX hours (ie. excludes 22h GMT Fri - 19h GMT Sun and New Year's Day)

        Parameters
        ----------
        data_frame : DataFrame
            data frame with FX prices

        Returns
        -------
        list(str)
        """
        # assume data_frame is in GMT time
        # remove Fri after 22:00 GMT
        # remove Sat
        # remove Sun before 19:00 GMT

        # Monday = 0, ..., Sunday = 6
        data_frame = data_frame[~((data_frame.index.dayofweek == 4) & (data_frame.index.hour > 22))]
        data_frame = data_frame[~((data_frame.index.dayofweek == 5))]
        data_frame = data_frame[~((data_frame.index.dayofweek == 6) & (data_frame.index.hour < 19))]
        data_frame = data_frame[~((data_frame.index.day == 1) & (data_frame.index.month == 1))]

        return data_frame

    def remove_duplicate_indices(self, df):
        return df[~df.index.duplicated(keep='first')]

    def mask_time_series_by_time(self, df, time_list, time_zone):
        """ Mask a time series by time of day and time zone specified
        e.g. given a time series minutes data
             want to keep data at specific time periods every day with a considered time zone

        Parameters
        ----------
        df : DateTime
            time series needed to be masked
        time_list : list of tuples
            deciding the time periods which we want to keep the data on each day
            e.g. time_list = [('01:08', '03:02'),('12:24','12:55'),('17:31','19:24')]
            * Note: assume no overlapping of these tuples
        time_zone: str
            e.g. 'Europe/London'

        Returns
        -------
        DataFrame  (which the time zone is 'UTC')
        """

        # Change the time zone from 'UTC' to a given one
        df.index = df.index.tz_convert(time_zone)
        df_mask = pd.DataFrame(0, index=df.index, columns=['mask'])

        # Mask data with each given tuple
        for i in range(0, len(time_list)):
            start_hour = int(time_list[i][0].split(':')[0])
            start_minute = int(time_list[i][0].split(':')[1])
            end_hour = int(time_list[i][1].split(':')[0])
            end_minute = int(time_list[i][1].split(':')[1])

            # E.g. if tuple is ('01:08', '03:02'),
            # take hours in target - take values in [01:00,04:00]
            narray = np.where(df.index.hour.isin(range(start_hour, end_hour + 1)), 1, 0)
            df_mask_temp = pd.DataFrame(index=df.index, columns=df_mask.columns.tolist(), data=narray)

            # Remove minutes not in target - remove values in [01:00,01:07], [03:03,03:59]
            narray = np.where(((df.index.hour == start_hour) & (df.index.minute < start_minute)), 0, 1)
            df_mask_temp = df_mask_temp * pd.DataFrame(index=df.index, columns=df_mask.columns.tolist(),
                                                           data=narray)
            narray = np.where((df.index.hour == end_hour) & (df.index.minute > end_minute), 0, 1)
            df_mask_temp = df_mask_temp * pd.DataFrame(index=df.index, columns=df_mask.columns.tolist(),
                                                           data=narray)

            # Collect all the periods we want to keep the data
            df_mask = df_mask + df_mask_temp

        narray = np.where(df_mask == 1, df, 0)
        df = pd.DataFrame(index=df.index, columns=df.columns.tolist(), data=narray)
        df.index = df.index.tz_convert('UTC')  # change the time zone to 'UTC'

        return df


#######################################################################################################################

class Calendar(object):
    """Provides calendar based functions for working out options expiries, holidays etc. Note, that at present, the
    expiry _calculations are approximate.

    """

    # Approximate mapping from tenor to number of business days
    _tenor_bus_day_dict = {'ON' : 1,
        'TN' : 2,
        '1W' : 5,
        '2W' : 10,
        '3W' : 15,
        '1M' : 20,
        '2M' : 40,
        '3M' : 60,
        '4M' : 80,
        '6M' : 120,
        '9M' : 180,
        '1Y' : 252,
        '2Y' : 252 * 2,
        '3Y' : 252 * 3,
        '5Y' : 252 * 5
    }

    def __init__(self):
        self._holiday_df = pd.read_parquet(constants.holidays_parquet_table)

    def flatten_list_of_lists(self, list_of_lists):
        """Flattens lists of obj, into a single list of strings (rather than characters, which is default behavior).

        Parameters
        ----------
        list_of_lists : obj (list)
            List to be flattened

        Returns
        -------
        str (list)
        """

        if isinstance(list_of_lists, list):
            rt = []
            for i in list_of_lists:
                if isinstance(i, list):
                    rt.extend(self.flatten_list_of_lists(i))
                else:
                    rt.append(i)

            return rt

        return list_of_lists

    def _get_full_cal(self, cal):
        holidays_list = []

        # Calendars which have been hardcoded in the parquet file (which users may also edit)
        if len(cal) == 6:
            # Eg. EURUSD (load EUR and USD calendars and combine the holidays)
            holidays_list.append([self._get_full_cal(cal[0:3]), self._get_full_cal(cal[3:6])])
        elif len(cal) == 9:
            holidays_list.append(
                [self._get_full_cal(cal[0:3]), self._get_full_cal(cal[3:6]), self._get_full_cal(cal[6:9])])
        else:
            if cal == 'FX':
                # Filter for Christmas & New Year's Day
                for i in range(1999, 2025):
                    holidays_list.append(pd.Timestamp(str(i) + "-12-25"))
                    holidays_list.append(pd.Timestamp(str(i) + "-01-01"))

            elif cal == 'NYD' or cal == 'NEWYEARSDAY':
                # Filter for New Year's Day
                for i in range(1999, 2025):
                    holidays_list.append(pd.Timestamp(str(i) + "-01-01"))

            elif cal == 'WDY' or cal == 'WEEKDAY':
                bday = CustomBusinessDay(weekmask='Sat Sun')

                holidays_list.append([x for x in pd.date_range('01 Jan 1999', '31 Dec 2025', freq=bday)])

            else:
                label = cal + ".holiday-dates"

                try:
                    holidays_list = self._holiday_df[label].dropna().tolist()
                except:
                    logger = LoggerManager().getLogger(__name__)
                    logger.warning(cal + " holiday calendar not found.")

        return holidays_list

    def create_calendar_bus_days(self, start_date, end_date, cal='FX'):
        """Creates a calendar of business days

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        end_date : DataFrame
            finish date of calendar
        cal : str
            business calendar to use

        Returns
        -------
        list
        """
        hols = self.get_holidays(start_date=start_date, end_date=end_date, cal=cal)

        return pd.bdate_range(start=start_date, end=end_date, freq='D', holidays=hols)

    def get_holidays(self, start_date=None, end_date=None, cal='FX', holidays_list=[]):
        """Gets the holidays for a given calendar

        Parameters
        ----------
        start_date : DateTime
            start date of calendar
        end_date : DataFrame
            finish date of calendar
        cal : str
            business calendar to use

        Returns
        -------
        list
        """
        # holidays_list ,  = []

        # TODO use Pandas CustomBusinessDays to get more calendars
        holidays_list = self._get_full_cal(cal)
        # .append(lst)

        # Use 'set' so we don't have duplicate dates if we are incorporating multiple calendars
        holidays_list = np.array(list(set(self.flatten_list_of_lists(holidays_list))))
        holidays_list = pd.to_datetime(holidays_list).sort_values()

        # Floor start date
        if start_date is not None:
            start_date = pd.Timestamp(start_date).floor('D')
            holidays_list = holidays_list[(holidays_list >= start_date)]

        if end_date is not None:
            # Ceiling end date
            end_date = pd.Timestamp(end_date).ceil('D')
            holidays_list = holidays_list[(holidays_list <= end_date)]

        # Remove all weekends unless it is WEEKDAY calendar
        if cal != 'WEEKDAY' or cal != 'WKY':
            holidays_list = holidays_list[holidays_list.dayofweek <= 4]

        return holidays_list.tz_localize('UTC')

    def get_business_days_tenor(self, tenor):
        if tenor in self._tenor_bus_day_dict.keys():
            return self._tenor_bus_day_dict[tenor]

        return None

    def get_dates_from_tenors(self, start, end, tenor, cal=None):
        freq = str(self.get_business_days_tenor(tenor)) + "B"
        return pd.DataFrame(index=pd.bdate_range(start, end, freq=freq))

    def get_delta_between_dates(self, date1, date2, unit='days'):
        if unit == 'days':
            return (date2 - date1).days

    def get_delivery_date_from_horizon_date(self, horizon_date, tenor, cal=None, asset_class='fx'):
        if 'fx' in asset_class:
            tenor_unit = ''.join(re.compile(r'\D+').findall(tenor))
            asset_holidays = self.get_holidays(cal=cal)

            if tenor_unit == 'ON':
                return horizon_date + CustomBusinessDay(n=1, holidays=asset_holidays)
            elif tenor_unit == 'TN':
                return horizon_date + CustomBusinessDay(n=2, holidays=asset_holidays)
            elif tenor_unit == 'SP':
                pass
            elif tenor_unit == 'SN':
                tenor_unit = 'D'
                tenor_digit = 1
            else:
                tenor_digit = int(''.join(re.compile(r'\d+').findall(tenor)))

            horizon_date = self.get_spot_date_from_horizon_date(horizon_date, cal, asset_holidays=asset_holidays)

            if 'SP' in tenor_unit:
                return horizon_date
            elif tenor_unit == 'D':
                return horizon_date + CustomBusinessDay(n=tenor_digit, holidays=asset_holidays)
            elif tenor_unit == 'W':
                return horizon_date + Day(n=tenor_digit * 7) + CustomBusinessDay(n=0, holidays=asset_holidays)
            else:
                if tenor_unit == 'Y':
                    tenor_digit = tenor_digit * 12

                horizon_period_end = horizon_date + CustomBusinessMonthEnd(tenor_digit + 1)
                horizon_floating = horizon_date + DateOffset(months=tenor_digit)

                cbd = CustomBusinessDay(n=1, holidays=asset_holidays)

                delivery_date = []

                if isinstance(horizon_period_end, pd.Timestamp):
                    horizon_period_end = [horizon_period_end]

                if isinstance(horizon_floating, pd.Timestamp):
                    horizon_floating = [horizon_floating]

                for period_end, floating in zip(horizon_period_end, horizon_floating):
                    if floating < period_end:
                        delivery_date.append(floating - cbd + cbd)
                    else:
                        delivery_date.append(period_end)

                return pd.DatetimeIndex(delivery_date)

    def get_expiry_date_from_horizon_date(self, horizon_date, tenor, cal=None, asset_class='fx-vol'):
        """Calculates the expiry date of FX options, based on the horizon date, the tenor and the holiday
        calendar associated with the asset.

        Uses expiry rules from Iain Clark's FX option pricing book

        Parameters
        ----------
        horizon_date : pd.Timestamp (collection)
            Horizon date of contract

        tenor : str
            Tenor of the contract

        cal : str
            Holiday calendar (usually related to the asset)

        asset_class : str
            'fx-vol' - FX options (default)

        Returns
        -------
        pd.Timestamp (collection)
        """
        if asset_class == 'fx-vol':

            tenor_unit = ''.join(re.compile(r'\D+').findall(tenor))

            asset_holidays = self.get_holidays(cal=cal)

            if tenor_unit == 'ON':
                tenor_digit = 1
            else:
                tenor_digit = int(''.join(re.compile(r'\d+') .findall(tenor)))

            if tenor_unit == 'D':
                return horizon_date + CustomBusinessDay(n=tenor_digit, holidays=asset_holidays)
            elif tenor_unit == 'W':
                return horizon_date + Day(n=tenor_digit * 7) + CustomBusinessDay(n=0, holidays=asset_holidays)
            else:
                horizon_date = self.get_spot_date_from_horizon_date(horizon_date, cal, asset_holidays=asset_holidays)

                if tenor_unit == 'M':
                    pass
                elif tenor_unit == 'Y':
                    tenor_digit = tenor_digit * 12

                horizon_period_end = horizon_date + CustomBusinessMonthEnd(tenor_digit + 1)
                horizon_floating = horizon_date + DateOffset(months=tenor_digit)

                cbd = CustomBusinessDay(n=1, holidays=asset_holidays)

                delivery_date = []

                if isinstance(horizon_period_end, pd.Timestamp):
                    horizon_period_end = [horizon_period_end]

                if isinstance(horizon_floating, pd.Timestamp):
                    horizon_floating = [horizon_floating]

                for period_end, floating in zip(horizon_period_end, horizon_floating):
                    if floating < period_end:
                        delivery_date.append(floating - cbd + cbd)
                    else:
                        delivery_date.append(period_end)

                delivery_date = pd.DatetimeIndex(delivery_date)

                return self.get_expiry_date_from_delivery_date(delivery_date, cal)

    def _get_settlement_T(self, asset):
        base = asset[0:3]
        terms = asset[3:6]

        if base in ['CAD', 'TRY', 'RUB'] or terms in ['CAD', 'TRY', 'RUB']:
            return 1

        return 2

    def get_spot_date_from_horizon_date(self, horizon_date, asset, asset_holidays=None):
        base = asset[0:3]
        terms = asset[3:6]

        settlement_T = self._get_settlement_T(asset)

        if asset_holidays is None:
            asset_holidays = self.get_holidays(cal=asset)

        # First adjustment step
        if settlement_T == 2:
            if base in ['MXN', 'ARS', 'CLP'] or terms in ['MXN', 'ARS', 'CLP']:
                horizon_date = horizon_date + BDay(1)
            else:
                if base == 'USD':
                    horizon_date = horizon_date + CustomBusinessDay(holidays=self.get_holidays(cal=terms))
                elif terms == 'USD':
                    horizon_date = horizon_date + CustomBusinessDay(holidays=self.get_holidays(cal=base))
                else:
                    horizon_date = horizon_date + CustomBusinessDay(holidays=asset_holidays)

        if 'USD' not in asset:
            asset_holidays = self.get_holidays(cal='USD' + asset)

        # Second adjustment step - move forward if horizon_date isn't a good business day in base, terms or USD
        if settlement_T <= 2:
            horizon_date = horizon_date + CustomBusinessDay(holidays=asset_holidays)

        return horizon_date

    def get_delivery_date_from_spot_date(self, spot_date, cal):
        pass

    def get_expiry_date_from_delivery_date(self, delivery_date, cal):
        base = cal[0:3]
        terms = cal[3:6]

        if base == 'USD':
             cal = terms
        elif terms == 'USD':
             cal = base

        hols = self.get_holidays(cal=cal + 'NYD')

        return delivery_date - CustomBusinessDay(self._get_settlement_T(cal), holidays=hols)

    def align_to_NY_cut_in_UTC(self, date_time, hour_of_day=10):

        tstz = Timezone()
        date_time = tstz.localize_index_as_new_york_time(date_time)
        date_time.index = date_time.index + timedelta(hours=hour_of_day)

        return tstz.convert_index_aware_to_UTC_time(date_time)

    def floor_date(self, data_frame):
        data_frame.index = data_frame.index.normalize()

        return data_frame

    def create_bus_day(self, start, end, cal=None):

        if cal is None:
            return pd.bdate_range(start, end)

        return pd.date_range(start, end, hols=self.get_holidays(start_date=start, end_date=end, cal=cal))

    def get_bus_day_of_month(self, date, cal='FX'):
        """ Returns the business day of the month (ie. 3rd Jan, on a Monday, would be the 1st business day of the month)
        """

        try:
            date = date.normalize()  # strip times off the dates - for business dates just want dates!
        except:
            pass

        start = pd.to_datetime(datetime.datetime(date.year[0], date.month[0], 1))
        end = datetime.datetime.today()  # pd.to_datetime(datetime.datetime(date.year[-1], date.month[-1], date.day[-1]))

        holidays = self.get_holidays(start_date=start, end_date=end, cal=cal)

        # bday = CustomBusinessDay(holidays=holidays, weekmask='Mon Tue Wed Thu Fri')

        bus_dates = pd.bdate_range(start, end, holidays=holidays)

        month = bus_dates.month

        work_day_index = np.zeros(len(bus_dates))
        work_day_index[0] = 1

        for i in range(1, len(bus_dates)):
            if month[i] == month[i - 1]:
                work_day_index[i] = work_day_index[i - 1] + 1
            else:
                work_day_index[i] = 1

        bus_day_of_month = work_day_index[bus_dates.searchsorted(date)]

        return bus_day_of_month

    def set_market_holidays(self, holiday_df):
        self._holiday_df = holiday_df

