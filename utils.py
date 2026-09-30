import pandas as pd
from itertools import product
from dateutil.relativedelta import relativedelta
from holidays.utils import country_holidays
from datetime import date, timedelta, datetime
import os 
import re
import numpy as np

def date_validation(year=None, month=None, date_range=None):
    cur_year = datetime.now().year
    results = [None, None, None]
    if year is not None:
        if type(year) is int: # a number
            if year > cur_year + 50 or year < cur_year - 100:
                return "(Year) Too far from today!"
            results[0] = [year]
        elif type(year) in (list, tuple): # a list
            if len(year) > 2:
                return "Too many inputs!"
            try:
                start, end = int(year[0]), int(year[1])
                if start > end:
                    return "Year range is not valid!"
                if start > cur_year + 50 or start < cur_year - 100 or end > cur_year + 50 or end < cur_year - 100:
                    return "Year range is not valid!"
                results[0] = (start, end)
            except:
                return "Year range is not valid!"
        elif type(year) is str: # a string of range
            try:
                years = re.split('[\W]+', year)
                if len(years) == 1:
                    results[0] = [int(year)]
                elif len(years) > 2:
                    return "Too many inputs!"
                else:
                    start, end = int(years[0]), int(years[1])
                    if start > end:
                        return "Year range is not valid!"
                    for yr in (start, end):
                        res = date_validation(year=yr)
                        if type(res) is str:
                            return res
                    results[0] = (start, end)
            except:
                return "Year range is not valid!"
    if month is not None:   
        if  type(month) is int: # a number
            if month not in range(1, 13):
                return "(Month) Too large/small!"
            results[1] = [month]
        elif type(month) in (list, tuple): # a list
            try:
                months = np.array([int(mo) for mo in month])
                if np.argwhere(months>12).size or np.argwhere(months<1).size:
                    return "Some month is not valid."
                results[1] = np.unique(months)
            except:
                return "Month list has problems!"
        elif re.search("\W", month): # a string of range
            try:
                months = np.array([int(mo) for mo in re.split('[\W]+', month)])
                if np.argwhere(months>12).size or np.argwhere(months<1).size:
                    return "Some month is not valid."
                results[1] = np.unique(months)
            except:
                return "Month range has problems!" 
    if date_range is not None:
        start_date, end_date = date_range[0], date_range[1]
        try:
            if type(start_date) is str:
                start_date, end_date = re.split("[\W]", start_date), re.split("[\W]", end_date)
                if len(start_date) not in (2, 3) or len(end_date) not in (2, 3):
                    return "Date range is invalid! Provide year-month or year-month-day."
                start_date = date(int(start_date[0]), int(start_date[1]), int(start_date[2])) if len(start_date) == 3 else date(int(start_date[0]), int(start_date[1]), 1)
                end_date = date(int(end_date[0]), int(end_date[1]), int(end_date[2])) if len(end_date) == 3 else date(int(end_date[0]), int(end_date[1]), 1) + relativedelta(months=1) - timedelta(days=1)
            if start_date > end_date:
                return "Date range is invalid!"
            results[2] = (start_date, end_date)
        except:
            return "Date range is invalid!"

    return results


def count_x_workdays(year_range=None, months=None, date_range=None,
                        inclusive="both",
                        save_folder=None, 
                        return_holidays=True, return_workdays=True,
                        include_juneteeth=False, 
                        include_good_friday=False, 
                        include_veterans=False, 
                        include_columbus=False,
                        christmas_shutdown=True):
    """
    This function is to count number of workdays.
    year_range: int or range
    months: int, list, or None. If None, the function will return result for the entire year.
    date_range: if provided, the workdays within the date range will be calculated.
    inclusive: whether to include both ends in the year range or only one end (left, right, none, both).
    save_folder: if provided, the result will be saved as excel file in the provided folder.
    """
    assert year_range is not None or date_range is not None, "Either year range or date range needs to be provided."

    process_dates = date_validation(year_range, months, date_range)
    assert type(process_dates) is not str, process_dates
    years, months, date_range = process_dates

    x_holidays, x_workdays = pd.DataFrame(), pd.DataFrame()

    if date_range:
        start_date, end_date = date_range
        if inclusive=='left':
            end_date = end_date - timedelta(days=1)
        elif inclusive=='right':
            start_date = start_date + timedelta(days=1)
        elif inclusive=='none':
            start_date += timedelta(days=1)
            end_date -= timedelta(days=1)
        date_range = (start_date, end_date)


    # get number of holidays per month for the years provided in the range for x
    # if date_range is provided, year_range will be ignored.
    x_holidays = list_x_holidays(year_range=years, 
                        date_range=date_range,
                        include_juneteeth=include_juneteeth, 
                        include_good_friday=include_good_friday, 
                        include_veterans=include_veterans, 
                        include_columbus=include_columbus,
                        christmas_shutdown=christmas_shutdown)

    if year_range:
        if inclusive=='left':
            years = range(years[0], years[-1])
        elif inclusive=='right':
            years = range(years[0]+1, years[-1]+1)
        elif inclusive=='none':
            years = range(years[0]+1, years[-1])
        else:
            years = range(years[0], years[-1]+1)

        if months is None:
            months = range(1, 13)

        # create dataframe with year-month column
        year_month = [f"{k}-{str(v).rjust(2,'0')}" for k, v in product(years, months)]
        x_workdays = pd.DataFrame(year_month, columns=['Year_Month'])
    
        x_workdays['Workdays'] = x_workdays.apply(lambda x: calculate_bdays(year_month=x.Year_Month, holidays=x_holidays.obs_date), axis=1)

    
    if date_range:
        num_workdays = calculate_bdays(date_range=date_range, holidays=x_holidays.obs_date)
        x_workdays = pd.DataFrame([date_range[0], date_range[1], num_workdays]).T
        x_workdays.columns = ['start_date', 'end_date', 'workdays']

    return_dfs = []

    if return_holidays:
        return_dfs.append(x_holidays)
    
    if return_workdays:
        return_dfs.append(x_workdays)

    if save_folder is not None:
        with pd.ExcelWriter(os.path.join(save_folder, "x_workdays.xlsx")) as f:
            x_holidays.to_excel(f, sheet_name='x Holidays', index=False)
            x_workdays.to_excel(f, sheet_name='x Workdays', index=False)
        
    return return_dfs



def calculate_bdays(holidays, year_month=None, date_range=None):
    start_date = datetime.now().date 
    end_date = datetime.now().date
    if year_month:
        year, month = int(year_month[:4]), int(year_month[-2:])    
        start_date, end_date = date(year, month, 1), date(year, month, 1) + relativedelta(months=1) - timedelta(days=1)
    if date_range:
        start_date, end_date = date_range
    
    bdays = pd.bdate_range(start_date, end_date, freq='C', holidays=holidays)
    num_workdays = len(bdays)
    return num_workdays


def list_x_holidays(year_range=None, date_range=None, 
                    include_juneteeth=False, 
                    include_good_friday=False, 
                    include_veterans=False,
                    include_columbus=False,
                    christmas_shutdown=True):
    """ 
    For a given year (range), return a dataframe of number of observed holidays in x.
    For Christmas shutdown, only list the start day of the shutdown.
    """
    assert year_range is not None or date_range is not None, "Either year range or date range needs to be provided."

    x_obs_holidays = ["New Year's Day", "Martin Luther King Jr. Day", "Memorial Day", "Independence Day", "Labor Day", "Thanksgiving", "Christmas Day"]

    if include_veterans:
        x_obs_holidays += ["Veterans Day"]

    if include_juneteeth:
        x_obs_holidays += ['Juneteenth National Independence Day']

    if include_columbus:
        x_obs_holidays += ['Columbus Day']
    
    years = [datetime.now().year]

    if year_range:
        years = [year_range] if type(year_range) is int else range(year_range[0], year_range[-1]+1)
    
    if date_range:
        years = range(date_range[0].year, date_range[1].year+1)

    # newer versions of `holidays` renamed "Thanksgiving" to "Thanksgiving Day"
    us_holidays = {(year, name.split(" (")[0].replace("Thanksgiving Day", "Thanksgiving")): dt for year in years for dt, name in country_holidays('US', years=year, observed=False).items()}
    x_holidays = {(year, name): dt for (year, name), dt in us_holidays.items() if name in x_obs_holidays}

    # get christmas eve
    christmas = {}
    for (year, name), dt in x_holidays.items():
        if name == 'Christmas Day':
            christmas.update({(dt.year, 'Christmas Eve'): dt - timedelta(days=1)})
    x_holidays.update(christmas)
    x_holidays = {(year, name): dt for (year, name), dt in x_holidays.items()}

    df = pd.DataFrame(x_holidays, index=['date']).T.reset_index()
    df.columns = ['year', 'holiday', 'date']

    # take care of thanksgiving two days
    def get_thanksgiving(ds):
        return pd.Series([ds.year, ds.holiday, date(ds.date.year, ds.date.month, ds.date.day+1)])
    dft = df[df.holiday=='Thanksgiving'].apply(get_thanksgiving, axis=1)
    dft.columns = df.columns

    df_final = pd.concat([df, dft], ignore_index=True).sort_values(by='date').reset_index(drop=True)

    # take care of good friday
    def get_good_friday(ds):
        """Calculates the date of Good Friday for a given year."""
        year = ds.year
        # Calculate Easter Sunday using the Meeus/Jones/Butcher algorithm
        a, b, c = year % 19, year // 100, year % 100
        d, e, f = b // 4, b % 4, (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = c // 4, c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        easter_sunday = date(year, month, day)
        good_friday = easter_sunday - timedelta(days=2)
        return pd.Series([ds.year, 'Good Friday', good_friday])

    if include_good_friday:
        dfg = df.drop_duplicates(subset='year').apply(get_good_friday, axis=1)
        dfg.columns = df.columns
        df_final = pd.concat([df_final, dfg], ignore_index=True).sort_values(by='date').reset_index(drop=True)


    # take care of observation day if any holiday is falling on weekends
    def get_observance(ds):
        dt = ds.date.weekday()
        obs_day = ds.date

        if dt == 5:
            obs_day = obs_day - timedelta(1) if ds.holiday != "New Year's Day" else ds.date + timedelta(2)
        elif dt == 6:
            obs_day += timedelta(1)

        return obs_day
    df_final['obs_date'] = df_final.apply(get_observance, axis=1)

    # take care of x shutdown week
    def get_shutdown_dates(dt):
        shutdown_dates = [date(dt.year, dt.month, day) for day in range(dt.day, 32)]
        df = pd.DataFrame(shutdown_dates, columns=['obs_date'])
        df['year'] = dt.year
        df['holiday'] = 'Christmas Shutdown'
        return df

    if christmas_shutdown:
        dfx = pd.concat(df_final[df_final.holiday.isin(['Christmas Eve'])].obs_date.apply(get_shutdown_dates).tolist(), ignore_index=True)
        df_final = df_final[~df_final.holiday.isin(['Christmas Eve', 'Christmas Day'])].copy()
        df_final = pd.concat([df_final, dfx], ignore_index=True).sort_values(by='obs_date').reset_index(drop=True)
        df_final.loc[df_final.date.isna(), 'date'] = df_final.loc[df_final.date.isna(), 'obs_date']

    df_final = df_final.drop(columns='date')

    if date_range:
        df_final = df_final[df_final.obs_date.between(date_range[0], date_range[1])].copy()
    
    return df_final