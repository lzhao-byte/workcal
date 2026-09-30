import streamlit as st
from datetime import datetime
from utils import *

@st.dialog("Range Input")
def get_range(formats):
    years, months, dates = None, None, None
    if formats == 'Year/Month':
        syr_col, eyr_col = st.columns([1,1])
        start = syr_col.text_input(label="Start Year", value=None, placeholder="Year (2024)")
        end = eyr_col.text_input(label="End Year (Optional)", value=None, placeholder="Year (2024)")
        years = start if start else years
        years = (start, end) if end else years
        months = st.text_input(label="Months (Optional)", value=None, placeholder="Month (2) or Months (2,4)")
    if formats == 'Date Range':
        start_col, end_col = st.columns([1,1])
        start_date = start_col.date_input("Start Date", value=None, format="YYYY-MM-DD")
        end_date = end_col.date_input("End Date", value=None, format="YYYY-MM-DD")
        dates = (start_date, end_date) if start_date or end_date else dates
    juneteenth = st.checkbox("Include Juneteenth?")
    good_friday = st.checkbox("Include Good Friday?")
    veteran = st.checkbox("Include Veteran's Day?")
    columbus = st.checkbox("Include Columbus Day?")
    christmas = st.checkbox("Have Christmas Shutdown?")
    if st.button("Submit"):
        st.session_state.range_input = {'year': years, 'month': months, 'date': dates}
        st.session_state.extras = {'juneteenth': juneteenth,
                                    'good_friday': good_friday,
                                    'veteran': veteran,
                                    'columbus': columbus,
                                    'christmas': christmas}
        st.rerun()

def generate_frame():
    cur_year = datetime.now().year

    st.write("""
    # Holidays and Workdays
    """)
    
    if "range_input" not in st.session_state:
        st.write("Select an option for workday calculation")
        ym, dr = "Year/Month", "Date Range"
        ym_col, dr_col = st.columns([1,1])
        if ym_col.button(ym, use_container_width=True):
            get_range(ym)
        if dr_col.button(dr, use_container_width=True):
            get_range(dr)
    else:
        years, months = st.session_state.range_input['year'], st.session_state.range_input['month']
        date_range = st.session_state.range_input['date']

        juneteenth = st.session_state.extras['juneteenth']
        good_friday = st.session_state.extras['good_friday']
        veteran = st.session_state.extras['veteran']
        columbus = st.session_state.extras['columbus']
        christmas = st.session_state.extras['christmas']

        try:
            return_dfs = count_x_workdays(year_range=years, months=months, date_range=date_range,
                            inclusive="both",
                            save_folder=None, 
                            return_holidays=True, return_workdays=True,
                            include_juneteeth=juneteenth, 
                            include_good_friday=good_friday, 
                            include_veterans=veteran, 
                            include_columbus=columbus,
                            christmas_shutdown=christmas)
            ho_tab, wo_tab = st.tabs(['Holidays', 'Workdays'])
            with ho_tab:
                if len(return_dfs[0]):
                    column_config={
                        "year": st.column_config.TextColumn("Year"),
                        "holiday": st.column_config.TextColumn("Holidays"),
                        "obs_date": st.column_config.DateColumn("Observed Date")
                    }
                    st.dataframe(return_dfs[0], use_container_width=True, hide_index=True, column_config=column_config)
            with wo_tab:
                if len(return_dfs[1]):
                    column_config={
                        "Year_Month": st.column_config.TextColumn("Month"),
                        "Workdays": st.column_config.NumberColumn("Workdays")
                    }
                    st.dataframe(return_dfs[1], use_container_width=True, hide_index=True, column_config=column_config)
        except AssertionError as msg:
            st.error(msg, icon=":material/error:")
        
        if st.button("Reset"):
            del st.session_state.range_input
            st.rerun()
        



if __name__ == "__main__":
    generate_frame()