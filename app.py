import streamlit as st
import numpy as np
import pandas as pd
import pygfunction as gt
import json
import base64
import requests
import mpu
import plotly.express as px
import json
import math
from PIL import Image
from GHEtool import Borefield, GroundData 
from plotly import graph_objects as go
from PIL import Image
from shapely.geometry import Point, shape
from streamlit_searchbox import st_searchbox
from streamlit_extras.no_default_selectbox import selectbox
import os
    

def hour_to_month(hourly_array, aggregation='sum'):
    result_array = []
    temp_value = 0 if aggregation in ['sum', 'max'] else []
    count = 0 if aggregation == 'average' else None
    for index, value in enumerate(hourly_array):
        if np.isnan(value):
            value = 0
        if aggregation == 'sum':
            temp_value += value
        elif aggregation == 'average':
            temp_value.append(value)
            count += 1
        elif aggregation == 'max' and value > temp_value:
            temp_value = value
        if index in [744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016, 8759]:
            if aggregation == 'average':
                if count != 0:
                    result_array.append(sum(temp_value) / count)
                else:
                    result_array.append(0)
                temp_value = []
                count = 0
            else:
                result_array.append(temp_value)
                temp_value = 0 if aggregation in ['sum', 'max'] else []
    return result_array

@st.cache_resource(show_spinner=False)
def import_spotprice(selected_year):
    df = pd.read_excel("src/csv/spotpriser.xlsx", sheet_name=selected_year)
    return df

def significant_digits(num):
    if isinstance(num, int):
        num_str = str(num).lstrip("-")  # Convert number to string and remove leading negative sign
        return len(num_str.rstrip("0"))  # Count the number of significant digits

    num_str = str(num).replace(".", "")  # Convert number to string and remove decimal point
    num_str = num_str.lstrip("0")  # Remove leading zeros
    return len(num_str)

class Calculator:
    def __init__(self):
        self.set_streamlit_settings()
        
        self.THERMAL_CONDUCTIVITY = 3.0
        self.GROUNDWATER_TABLE = 10
        self.DEPTH_TO_BEDROCK = 10
        self.BUILDING_TYPE = "A"
        self.BUILDING_STANDARD = "X"
        
        self.MINIMUM_TEMPERATURE = -1
        self.BOREHOLE_BURIED_DEPTH = 10
        self.BOREHOLE_RADIUS = (115/1000)/2
        self.BOREHOLE_SIMULATION_YEARS = 30
        self.EFFECT_COVERAGE = 85

        self.MAXIMUM_DEPTH = 300
        self.COST_HEAT_PUMP_PER_KW = 12000
        self.PAYMENT_TIME = 30
        self.INTEREST = 5.0
        
        self.ELPRICE_REGIONS = {
        'NO 1': 'Sørøst-Norge (NO1)',
        'NO 2': 'Sørvest-Norge (NO2)',
        'NO 3': 'Midt-Norge (NO3)',
        'NO 4': 'Nord-Norge (NO4)',
        'NO 5': 'Vest-Norge (NO5)'
        }
        
        self.ELPRICE_REGIONS_BACK = {
        'Sørøst-Norge (NO1)': 'NO1',
        'Sørvest-Norge (NO2)': 'NO2',
        'Midt-Norge (NO3)': 'NO3',
        'Nord-Norge (NO4)': 'NO4',
        'Vest-Norge (NO5)': 'NO5'
        }
    
    def set_streamlit_settings(self):
        st.set_page_config(
        page_title="Bergvarmekalkulatoren",
        page_icon="♨️",
        layout="wide",
        initial_sidebar_state="collapsed")
        
        with open("src/styles/main.css") as f:
            st.markdown("<style>{}</style>".format(f.read()), unsafe_allow_html=True)

        st.markdown(
        """
            <style>
                .appview-container .main .block-container {{
                    padding-top: {padding_top}rem;
                    padding-bottom: {padding_bottom}rem;
                    }}

            </style>""".format(
            padding_top=1, padding_bottom=1
        ),
        unsafe_allow_html=True,
        )

        st.markdown(
            """
            <style>
            [data-testid="collapsedControl"] svg {
                height: 4rem;
                width: 4rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
            )
       
    def streamlit_input_container(self):
        def __streamlit_onclick_function():
            st.session_state.is_expanded = False  
        if 'is_expanded' not in st.session_state:
            st.session_state.is_expanded = True
        container = st.expander("Opplysninger om din bolig", expanded = st.session_state.is_expanded)
        with container:
            # -- Input content
            self.__streamlit_calculator_input()
            # -- Input content
            start_calculation = st.button("Start kalkulator for min bolig", on_click=__streamlit_onclick_function)
            if 'load_state' not in st.session_state:
                st.session_state.load_state = False
        if start_calculation or st.session_state.load_state:
            self.progress_bar = st.progress(0, text="Laster inn...")
            st.toast("Beregner ...", icon = "💻")
            st.session_state.load_state = True
            # initialize logging
            if 'log' not in st.session_state:
                st.session_state['log'] = False
            if st.session_state["log"] == False:
                if self.building_age == "Før 2007":
                    self.building_age = "Eldre enn 2007"
                else:
                    self.building_age = "Nyere enn 2007"
                log_data = {
                    "Postnummer": self.address_postcode,
                    "Areal": int(self.building_area),
                    "Byggeaar": self.building_age,
                    "Vannbaaren varme": self.waterborne_heat_option,
                    "Type vannbaarent varmesystem": self.selected_cop_option
                }

                file_path = 'log_file.json'
                file_exists = os.path.exists(file_path)
                if file_exists and os.path.getsize(file_path) > 0:
                    with open(file_path, 'r') as file:
                        existing_data = json.load(file)
                else:
                    existing_data = []
                new_key = len(existing_data)
                existing_data.append((new_key, log_data))
                with open(file_path, 'w') as file:
                    json.dump(existing_data, file, indent=4)
                st.session_state["log"] = True
        else:
            st.stop()
            
    def __streamlit_calculator_input(self):
        st.header("Bergvarmekalkulatoren")
        st.write("""Med bergvarmekalkulatoren kan du raskt 
                 beregne potensialet for å hente energi fra bakken 
                 til din bolig! Start med å skrive inn adresse i søkefeltet under.""")
        self.__streamlit_address_input()
        c1, c2 = st.columns(2)
        with c1:
            self.__streamlit_area_input()
        with c2:
            self.__streamlit_age_input()
        c1, c2 = st.columns(2)
        with c1:
            state = self.__streamlit_waterborne_heat_input()
        with c2:
            self.__streamlit_heat_system_input()
        if state == False:
            st.stop()
        # temperaturdata
        self.__get_temperature_data()
        # strømpriser
        self.__find_elprice_region()
        # energibehov
        self.__profet_calculation()
        self.__streamlit_demand_input()
         
    
    def __streamlit_address_input(self):
        def __address_search(searchterm):
            if not searchterm:
                return []
            number_of_addresses = 5
            r = requests.get(f"https://ws.geonorge.no/adresser/v1/sok?sok={searchterm}&fuzzy=false&treffPerSide={number_of_addresses}&sokemodus=OR", auth=('user', 'pass'))
            if r.status_code == 200 and len(r.json()["adresser"]) == number_of_addresses:
                response = r.json()["adresser"]
            else:
                return []
            return [
                (
                    f"{address['adressetekst']}, {address['poststed'].capitalize()}",
                    [f"{address['adressetekst']}, {address['poststed']}",f"{address['representasjonspunkt']['lat']}", f"{address['representasjonspunkt']['lon']}", f"{address['postnummer']}", f"{address['kommunenavn']}"]
                )
                for address in response
            ]
        #--
        selected_adr = st_searchbox(
            __address_search,
            key="address_search",
            placeholder = "Adresse 🏠",
            clear_on_submit = False
        )
        if selected_adr != None:
            try:
                self.address_name = selected_adr[0]
                address_str = self.address_name.split(",")[0]
                address_str_first_char = address_str[0]
                if address_str_first_char.isdigit():
                    # gnr/bnr
                    self.address_str = address_str_first_char
                else:
                    # vanlig
                    self.address_str = address_str.replace(" ", "+")
            except Exception:
                st.warning("Fyll inn adresse på nytt", icon="⚠️")
                st.stop()
            self.address_lat = float(selected_adr[1])
            self.address_long = float(selected_adr[2])
            self.address_postcode = selected_adr[3]
            self.kommunenavn = selected_adr[4].capitalize()
            #--
            #streamlit_root_logger.info = "Adresse fylt inn"
        else:
            #st_lottie("src/csv/house.json")
            #image = Image.open('src/data/figures/Ordinary day-amico.png')
            image = Image.open("src/data/figures/nylogo.png")
            st.image(image)
            st.stop()
            
    def __area_input(self):
        #number = st.number_input('1. Skriv inn oppvarmet boligareal [m²]', value = None, step = 10, help = "Boligarealet som tilføres varme fra boligens varmesystem.")
        
        number = st.text_input('1. Skriv inn oppvarmet boligareal [m²]', help = "Boligarealet som tilføres varme fra boligens varmesystem.")
        #if number != None:
        if number.isdigit():
            number = float(number)
            if number < 120:
                st.error("For boliger som har mindre enn 120 m² oppvarmet areal er varmebehovet vanligvis så lavt at bergvarme blir uforholdsmessig dyrt.")
                st.stop()
            elif number > 500:
                st.error("Boligareal kan ikke være større enn 500 m².")
                st.stop()
        elif number == 'None' or number == '':
            number = 0
        else:
            st.error('Input må være et tall.', icon="⚠️")
            number = 0
        return number
    
    def __streamlit_age_input(self):
        #c1, c2 = st.columns(2)
        #with c2:
        #    st.info("Bygningsstandard brukes til å anslå oppvarmingsbehovet for din bolig")
        #with c1:
        selected_option = selectbox("Når ble boligen bygget?", options = ["Før 2007", "Etter 2007"], no_selection_label = "Velg et alternativ", help = "Bygningsstandard brukes til å anslå oppvarmingsbehovet for din bolig.")
        if selected_option == None:
            st.stop()
        elif selected_option == "Før 2007":
            self.BUILDING_STANDARD = "X"
        elif selected_option == "Etter 2007":
            self.BUILDING_STANDARD = "Y"
            
        if self.building_area == 0:
            st.stop()
        self.building_age = selected_option
                
    def __streamlit_area_input(self):
        #c1, c2 = st.columns(2)
        #with c2:
        #st.info("Boligarealet som tilføres varme fra boligens varmesystem")
        #with c1:
        self.building_area = self.__area_input()

        
    def __streamlit_heat_system_input(self):
        option_list = ['Gulvvarme', 'Radiator', 'Gulvvarme og radiator']
        #c1, c2 = st.columns(2)
        #with c1:
        if self.waterborne_heat_cost == 0:
            text = "type"
        else:
            text = "ønsket"
        selected = selectbox(f"Velg {text} vannbårent varmesystem", options = option_list, no_selection_label = "Velg et alternativ", help = "Hvordan fordeles varmen i boligen din?")
        if selected == None:
            st.stop()
        else:
            self.selected_cop_option = selected
                
    def __streamlit_waterborne_heat_input(self):
        selected_option = selectbox("Har boligen vannbåren varme?", options = ["Ja", "Nei"], no_selection_label = "Velg et alternativ", help = "Bergvarme krever at boligen har et vannbårent varmesystem.")
        if selected_option == None:
            self.waterborne_heat_cost = 0
            state = False
        elif selected_option == "Nei":
            self.waterborne_heat_cost = self.__rounding_to_int(20000 + 815 * self.building_area)
            state = True
        elif selected_option == "Ja":
            self.waterborne_heat_cost = 0
            state = True
        self.waterborne_heat_option = selected_option
        return state
    
    def __space_heating_input(self, demand_old):
        number = st.number_input('1. Justere oppvarmingsbehovet [kWh/år]?', value = demand_old, step = 1000, help = "For en gjennomsnittlig norsk husholdning med panelovner utgjør oppvarmingsbehovet ca. 60 % av det årlige strømforbruket.")
        #if number.isdigit():
            #number = float(number)
        if number < 13000:
            st.error("Hvis reelt oppvarmingsbehov i boligen din er lavt (under 13 000 kWh per år), er bergvarme en mindre lønnsom investering.")
            st.markdown(f'<a target="parent" style="font-size: 1.0rem; border-radius: 15px; text-align: center; padding: 1rem; min-height: 60px; display: inline-block; box-sizing: border-box; width: 100%; transition: background-color 0.3s;" href="https://www.varmepumpeinfo.no/forhandler?postnr={self.address_postcode}&adresse={self.address_str}">Vis lokale forhandlere med luft-til-luft-varmepumper her</a>', unsafe_allow_html=True)
            st.stop()
        elif number > 100000:
            st.error("Denne bergvarmekalkulatoren er spesialdesignet for småhus og ikke egnet for romoppvarmingsbehov større enn 100 000 kWh/år.")
            st.markdown(f'<a target="parent" style="font-size: 1.0rem; border-radius: 15px; text-align: center; padding: 1rem; min-height: 60px; display: inline-block; box-sizing: border-box; width: 100%; transition: background-color 0.3s;" href="https://www.varmepumpeinfo.no/forhandler?postnr={self.address_postcode}&adresse={self.address_str}">Ta kontakt med en lokal forhandler!</a>', unsafe_allow_html=True)
            st.stop()
#        elif number == 'None':
#            number = 0
#        elif number == '':
#            st.error("Input må være et tall")
#            st.stop()
#        else:
#            st.error('Input må være et tall')
#            st.stop()
        return number
    
    def __dhw_input(self, demand_old):
        number = st.number_input('1. Justere varmtvannsbehovet [kWh/år]?', value = demand_old, step = 1000, help = "Oppvarming av varmtvann utgjør ca. 15% av årlig strømforbruk, men det avhenger av hvor mange personer som bor i boligen.")
        #if number.isdigit():
        #number = float(number)
        if number < 0:
            st.error("Verdien kan ikke være mindre enn 0 kWh/år.")
            st.stop()
        elif number > 20000:
            st.error("Denne bergvarmekalkulatoren er spesialdesignet for småhus og ikke egnet for varmtvannsbehov større enn 20 000 kWh/år.")
            st.markdown(f'<a target="parent" style="font-size: 1rem; border-radius: 15px; text-align: center; padding: 1rem; min-height: 60px; display: inline-block; box-sizing: border-box; width: 100%; transition: background-color 0.3s;" href="https://www.varmepumpeinfo.no/forhandler?postnr={self.address_postcode}&adresse={self.address_str}">Ta kontakt med en lokal forhandler!</a>', unsafe_allow_html=True)
            st.stop()
#        elif number == 'None':
#            number = 0
#        elif number == '':
#            st.error("Input må være et tall")
#            st.stop()
#        else:
#            st.error('Input må være et tall')
#            st.stop()
        return number
            
    def __streamlit_demand_input(self):
        demand_sum_old = self.__rounding_to_int_demand(np.sum(self.dhw_demand + self.space_heating_demand))
        dhw_demand_old = self.__rounding_to_int_demand(np.sum(self.dhw_demand))
        space_heating_demand_old = self.__rounding_to_int_demand(np.sum(self.space_heating_demand))
        if (dhw_demand_old + space_heating_demand_old) != demand_sum_old:
            difference = demand_sum_old - (dhw_demand_old + space_heating_demand_old)
            space_heating_demand_old = space_heating_demand_old + difference
        st.info(f"""➭ Vi estimerer at din bolig trenger **{demand_sum_old:,} kWh** 
                til oppvarming og varmtvann i året. Her inngår et oppvarmingsbehov 
                på {space_heating_demand_old:,} kWh og et varmtvannsbehov på {dhw_demand_old:,} kWh. 
                """.replace(",", " "))
#        st.info(f"""ⓘ Vi beregner varmebehovet på en forenklet måte ut fra erfaringstall 
#                fra østlandsklima. Vi anbefaler deg å legge inn mest mulig reelle verdier 
#                for din bolig, spesielt hvis du bor i et kaldt eller et mildt klima.
#                """.replace(",", " "))
        st.write("")
        st.write("")  
        c1, c2 = st.columns(2)
        with c1:
            space_heating_demand_new = self.__space_heating_input(demand_old = space_heating_demand_old)
        with c2:
            dhw_demand_new = self.__dhw_input(demand_old = dhw_demand_old)
        dhw_percentage = dhw_demand_new / dhw_demand_old
        space_heating_percentage = space_heating_demand_new / space_heating_demand_old
        self.dhw_demand = (self.dhw_demand * dhw_percentage).flatten()
        self.space_heating_demand = (self.space_heating_demand * space_heating_percentage).flatten()
        #
        if dhw_percentage != 1 or space_heating_percentage != 1:
            st.info(f"Justert årlig behov for oppvarming og varmtvann: **{self.__rounding_to_int(space_heating_demand_new + dhw_demand_new):,} kWh**.".replace(",", " "), icon="ℹ️")
            

    def __get_temperature_data(self):
        # find closest weather station
        distance_min = 1000000
        df = pd.read_csv('src/data/temperature/Stasjoner.csv', sep=',',on_bad_lines='skip')
        for i in range (0, len (df)):
            distance = mpu.haversine_distance((df.iat [i,1], df.iat [i,2]), (self.address_lat, self.address_long))
            if distance != 0 and distance < distance_min:
                distance_min = distance
                self.weatherstation_id = df.iat[i,0]
                self.weatherstation_lat = df.iat[i,1]
                self.weatherstation_long = df.iat[i,2]
                self.weatherstation_distance = distance_min
        # get temperature array
        temperature_array = 'src/data/temperature/_' + self.weatherstation_id + '_temperatur.csv'
        self.temperature_arr = pd.read_csv(temperature_array, sep=',', on_bad_lines='skip').to_numpy()
        self.average_temperature = float("{:.2f}".format(np.average(self.temperature_arr)))
        
    def __find_elprice_region(self):
        # import json function
        def __import_json():
            with open('src/csv/regioner.geojson') as f:
                js = json.load(f)
            f.close()
            return js
        json_file = __import_json()
        # find region
        region = 'NO 1'
        for feature in json_file['features']:
            polygon = shape(feature['geometry'])
            if polygon.contains(Point(self.address_long, self.address_lat)):
                region = feature['properties']['ElSpotOmr']
        self.elprice_region = self.ELPRICE_REGIONS[region]
        

    def __find_municipality_temperatures(self):
        municipality_name = self.kommunenavn
        df = pd.read_excel("src/csv/temperaturer_kommuner.xlsx")
        df_kommune = df[df['Kommune'] == municipality_name].reset_index(drop = True)
        df_oslo = df[df['Kommune'] == "Oslo"].reset_index(drop = True)
            
        graddag_oslo = float(df_oslo['Graddagstall'].iloc[0])
        dut_oslo = float(df_oslo['DUTv'].iloc[0])
        if len(df_kommune) > 0:
            graddag_kommune = float(df_kommune['Graddagstall'].iloc[0])
            dut_kommune = float(df_kommune['DUTv'].iloc[0])
        else:
            graddag_kommune = graddag_oslo
            dut_kommune = dut_oslo
        return graddag_oslo, graddag_kommune, dut_kommune

    def __effect_calculation(self, energy_demand, dut, graddagstall):
        Q = energy_demand
        T_in = 23
        k = 5
        DUTv = dut
        G_year = graddagstall
        effect = (Q * (T_in + k - DUTv))/(G_year * 24)
        return effect
        
    def __profet_calculation(self):
        #--
        graddag_referanse, graddag_adresse, dut_adresse = self.__find_municipality_temperatures()
        #--
        profet_data_df = pd.read_csv('src/data/demand/profet_data.csv', sep = ";")
        space_heating_series = profet_data_df[f"{self.BUILDING_TYPE}_{self.BUILDING_STANDARD}_SPACEHEATING"]
        self.space_heating_demand = (self.building_area * np.array(space_heating_series))
        dhw_heating_series = profet_data_df[f"{self.BUILDING_TYPE}_{self.BUILDING_STANDARD}_DHW"]
        self.dhw_demand = (self.building_area * np.array(dhw_heating_series))
        self.dhw_demand = (25*self.building_area/np.sum(self.dhw_demand)) * self.dhw_demand
        electric_demand_series = profet_data_df[f"{self.BUILDING_TYPE}_{self.BUILDING_STANDARD}_ELECTRIC"]
        self.electric_demand = self.building_area * np.array(electric_demand_series)
        #--
        forholdstall = graddag_adresse/graddag_referanse
        self.space_heating_demand  = self.space_heating_demand * forholdstall
        self.dut_effect = self.__rounding_to_int(self.__effect_calculation(energy_demand = np.sum(self.space_heating_demand), dut = dut_adresse, graddagstall = graddag_adresse))
        #--
    
    def __streamlit_sidebar_settings(self):
        image = Image.open("src/data/figures/bergvarmekalkulatoren_logo_blå.png")
        st.image(image)
        st.header("Forutsetninger")
        st.write("Her kan du justere forutsetningene som ligger til grunn for beregningene.")

    def environmental_calculation(self):
        self.geoenergy_emission_series = (self.compressor_series + self.peak_series) * self.emission_constant_electricity
        self.direct_el_emission_series = (self.dhw_demand + self.space_heating_demand) * self.emission_constant_electricity
        self.emission_savings = self.__rounding_to_int((np.sum(self.direct_el_emission_series - self.geoenergy_emission_series) * self.BOREHOLE_SIMULATION_YEARS) / 1000)
        self.emission_savings_flights = self.__rounding_to_int(self.emission_savings/(90/1000))

    def cost_calculation(self):
        # -- investeringskostnader
        if self.waterborne_heat_cost > 0:
            self.enova_tilskudd = 40000
        else:
            self.enova_tilskudd = 15000
        self.geoenergy_investment_cost = self.__rounding_to_int(20000 + (self.borehole_depth * self.number_of_boreholes) * 437.5) # brønn + graving
        self.heat_pump_cost = self.__rounding_to_int(214000 + (self.heat_pump_size) * 2200) # varmepumpe
        self.investment_cost = self.geoenergy_investment_cost + self.heat_pump_cost + self.waterborne_heat_cost 
        # -- driftskostnader
        self.direct_el_operation_cost = self.calculate_el_cost(self.dhw_demand + self.space_heating_demand) # kostnad direkte elektrisk
        self.geoenergy_operation_cost = self.calculate_el_cost(self.compressor_series + self.peak_series) # kostnad grunnvarme

        #self.direct_el_operation_cost = (self.dhw_demand + self.space_heating_demand) * self.elprice # kostnad direkte elektrisk
        #self.geoenergy_operation_cost = (self.compressor_series + self.peak_series) * self.elprice # kostnad grunnvarme 
        self.savings_operation_cost = self.__rounding_to_int(np.sum(self.direct_el_operation_cost - self.geoenergy_operation_cost)) # besparelse
        self.savings_operation_cost_lifetime = self.savings_operation_cost * self.BOREHOLE_SIMULATION_YEARS
        # -- lån
        total_number_of_months = self.PAYMENT_TIME * 12
        amortisering = self.investment_cost / total_number_of_months
        prosentandel_renter = self.investment_cost * (self.INTEREST/100) / 12
        self.loan_cost_monthly = amortisering + prosentandel_renter
        self.loan_cost_yearly = self.loan_cost_monthly * 12
        # -- visningsvariabler
        self.short_term_investment = self.__rounding_to_int(self.savings_operation_cost)
        self.long_term_investment = self.__rounding_to_int(self.savings_operation_cost_lifetime - self.investment_cost)
        # -- lån
        self.short_term_loan = self.__rounding_to_int(self.savings_operation_cost - self.loan_cost_yearly)
        self.long_term_loan = self.__rounding_to_int((self.savings_operation_cost - self.loan_cost_yearly) * self.BOREHOLE_SIMULATION_YEARS)
        
    def __plot_costs_loan(self):
        x = [i for i in range(0, self.BOREHOLE_SIMULATION_YEARS + 1)]
        y_1 = (np.sum(self.geoenergy_operation_cost) + (self.loan_cost_monthly * 12)) * np.array(x)
        y_2 = np.sum(self.direct_el_operation_cost) * np.array(x)
        fig = go.Figure(data = [
            go.Scatter(
                x=x,
                y=y_1,
                mode='lines',
                hoverinfo='skip',
                marker_color = "#48a23f",
                name=f"Bergvarme (lån):<br>{self.__rounding_costs_to_int(np.max(y_1)):,} kr".replace(",", " "),
            )
            , 
            go.Scatter(
                x=x,
                y=y_2,
                mode='lines',
                hoverinfo='skip',
                marker_color = "#880808",
                name=f"Direkte elektrisk<br>oppvarming:<br>{self.__rounding_costs_to_int(np.max(y_2)):,} kr".replace(",", " "),
            )])
        fig["data"][0]["showlegend"] = True
        fig.update_layout(legend=dict(itemsizing='constant'))
        fig["data"][0]["showlegend"] = True
        fig.update_layout(
            legend_title = "Kostnad etter 30 år:",
            legend_title_font=dict(size=16),
            legend_font=dict(size=16),
            autosize=True,
            margin=dict(l=0,r=0,b=10,t=10,pad=0),
            yaxis_title="Oppvarmingskostnader [kr]",
            plot_bgcolor="white",
            legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0)"),
            xaxis = dict(
                tickmode = 'array',
                tickvals = [i for i in range(1, self.BOREHOLE_SIMULATION_YEARS + 1, 3)],
                ticktext = [f"År {i}" for i in range(1, self.BOREHOLE_SIMULATION_YEARS + 1, 3)]
                ))
        fig.update_xaxes(
            range=[0, 31],
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_yaxes(
            tickformat=",",
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_layout(separators="* .*")
        return fig
    
    def __plot_costs_monthly(self, geoenergy_operation_cost, direct_el_operation_cost, y_max=None, y_min=None):
        y_1 = np.concatenate((geoenergy_operation_cost[6:], geoenergy_operation_cost[:6]))
        y_2 = np.concatenate((direct_el_operation_cost[6:], direct_el_operation_cost[:6]))
        x = ['jul', 'aug', 'sep', 'okt', 'nov', 'des', 'jan', 'feb', 'mar', 'apr', 'mai', 'jun']
        fig = go.Figure(data = [
            go.Bar(
                x=x,
                y=y_1,
                #mode='lines',
                hoverinfo='skip',
                marker_color = "#48a23f",
                name=f"Bergvarme:<br>{self.__rounding_costs_to_int(np.sum(y_1)):,} kr/år".replace(",", " "),
            )
            , 
            go.Bar(
                x=x,
                y=y_2,
                #mode='lines',
                hoverinfo='skip',
                marker_color = "#880808",
                name=f"Direkte elektrisk<br>oppvarming:<br>{self.__rounding_costs_to_int(np.sum(y_2)):,} kr/år".replace(",", " "),
            )])
        fig["data"][0]["showlegend"] = True
        fig.update_layout(legend=dict(itemsizing='constant'))
        fig.update_layout(
            legend_title = "Månedlige kostnader:",
            legend_title_font=dict(size=16),
            legend_font=dict(size=16),
            autosize=True,
            margin=dict(l=0,r=0,b=10,t=10,pad=0),
            yaxis_title="Oppvarmingskostnader [kr]",
            plot_bgcolor="white",
            legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0)"),
        )
        fig.update_xaxes(
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_yaxes(
            range=[y_min, y_max],
            tickformat=",",
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_layout(separators="* .*")
        return fig
    
    def __plot_costs_investment(self):
        x = [i for i in range(0, self.BOREHOLE_SIMULATION_YEARS + 1)]
        y_1 = np.sum(self.geoenergy_operation_cost) * np.array(x) + self.investment_cost
        y_2 = np.sum(self.direct_el_operation_cost) * np.array(x)
        fig = go.Figure(data = [
            go.Scatter(
                x=x,
                y=y_1,
                mode='lines',
                hoverinfo='skip',
                marker_color = "#48a23f",
                name=f"Bergvarme:<br>{self.__rounding_costs_to_int(np.max(y_1)):,} kr".replace(",", " "),
            )
            , 
            go.Scatter(
                x=x,
                y=y_2,
                mode='lines',
                hoverinfo='skip',
                marker_color = "#880808",
                name=f"Direkte elektrisk<br>oppvarming:<br>{self.__rounding_costs_to_int(np.max(y_2)):,} kr".replace(",", " "),
            )])
        fig["data"][0]["showlegend"] = True
        fig.update_layout(legend=dict(itemsizing='constant'))
        fig.update_layout(
            legend_title = "Kostnad etter 30 år:",
            legend_title_font=dict(size=16),
            legend_font=dict(size=16),
            autosize=True,
            margin=dict(l=0,r=0,b=10,t=10,pad=0),
            yaxis_title="Oppvarmingskostnader [kr]",
            plot_bgcolor="white",
            legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0)"),
            xaxis = dict(
                tickmode = 'array',
                tickvals = [i for i in range(1, self.BOREHOLE_SIMULATION_YEARS + 1, 3)],
                ticktext = [f"År {i}" for i in range(1, self.BOREHOLE_SIMULATION_YEARS + 1, 3)]
                ))
        fig.update_xaxes(
            range=[0, 31],
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_yaxes(
            tickformat=",",
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_layout(separators="* .*")
        return fig
        
    def __plot_environmental(self):
        geoenergy_emission = self.__rounding_to_int_demand(np.sum(self.compressor_series + self.peak_series))
        direct_el_emmision = self.__rounding_to_int_demand(np.sum(self.dhw_demand + self.space_heating_demand))
        emission_savings = self.__rounding_to_int_demand(np.sum(self.delivered_from_wells_series))  
        col1, col2 = st.columns(2)
        with col1:
            source = pd.DataFrame({"label" : [f'Strøm: {geoenergy_emission:,} kWh/år'.replace(","," "), f'Fra brønner: {(direct_el_emmision-geoenergy_emission):,} kWh/år'.replace(","," ")], "value": [geoenergy_emission, emission_savings]})
            fig = px.pie(source, names='label', values='value', color_discrete_sequence = ['#48a23f', '#a23f47'], hole = 0.4)
            fig.update_layout(
            margin=dict(t=50, b=50),
            legend=dict(orientation='h', y=1.3),
            plot_bgcolor="white",
            legend_title_text = "Bergvarme",
            legend_title_font=dict(size=16),
            legend_font=dict(size=16),
            autosize=True,
            )
            custom_texttemplate = '%{percent}'.replace(".", ",")
            fig.update_traces(textinfo='percent', textfont_size=16, texttemplate=custom_texttemplate)
            st.plotly_chart(figure_or_data = fig, use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
        with col2:
            source = pd.DataFrame({"label" : [f'Strøm: {direct_el_emmision:,} kWh/år'.replace(","," ")], "value": [direct_el_emmision]})
            fig = px.pie(source, names='label', values='value', color_discrete_sequence = ['#a23f47'], hole = 0.4)
            fig.update_layout(
            margin=dict(t=50, b=50),
            legend=dict(orientation='h', y=1.3),
            plot_bgcolor="white",
            legend_title_text = "Direkte elektrisk oppvarming",
            legend_title_font=dict(size=16),
            legend_font=dict(size=16),
            autosize=True,
            )
            fig.update_traces(textinfo='none')
            st.plotly_chart(figure_or_data = fig, use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})

    def streamlit_calculations(self):
        with st.sidebar:
            self.__streamlit_sidebar_settings()
            self.__streamlit_adjust_input()
        # grunnvarmeberegning
        self.borehole_calculation()
        # stømsparingsberegning
        self.environmental_calculation()
        # kostnadsberegning
        self.cost_calculation() 
        

    def __streamlit_adjust_input(self):
        with st.form('input'):
            self.__adjust_heat_pump_size()
            self.__adjust_cop()
            self.__adjust_elprice()  
            self.__adjust_energymix()
            self.__adjust_interest()                            
            st.form_submit_button('Oppdater')
                
    def __adjust_cop(self):
        space_heating_sum = np.sum(self.space_heating_demand)
        cop_gulvvarme, cop_radiator, self.DHW_COP = 0, 0, 2
        if self.selected_cop_option == "Gulvvarme":
            cop_gulvvarme = 4.0
        elif self.selected_cop_option == "Radiator":
            cop_radiator = 3.0
        elif self.selected_cop_option == "Gulvvarme og radiator":
            cop_gulvvarme = 4.0
            cop_radiator = 3.0
        if cop_gulvvarme > 0 and cop_radiator > 0:
            space_heating = ((cop_gulvvarme + cop_radiator)/2) * space_heating_sum
        elif cop_gulvvarme > 0 and cop_radiator == 0:
            space_heating = cop_gulvvarme * space_heating_sum
        elif cop_gulvvarme == 0 and cop_radiator > 0:
            space_heating = cop_radiator * space_heating_sum
        combined_cop = (space_heating) / (space_heating_sum)
        self.COMBINED_COP = float(st.number_input(
            "Årsvarmefaktor", 
            help = """Varmefaktor eller COP (coeficcient of performance) beskriver ytelsen 
            til varmepumper der og da. Årsvarmefaktoren er hvor effektivt en varmepumpe produserer varme i løpet av et år.""", 
            value = float(combined_cop), step = 0.1, min_value = 2.0, max_value= 5.0))

    def __nettleie_energiledd(self, row):
        hour = row['Dato/klokkeslett'].hour
        month = row['Dato/klokkeslett'].month
        weekday = row['Dato/klokkeslett'].weekday()
        if (0 <= hour < 6) or (22 <= hour <= 23) or (weekday in [5,6]): # night
            if (month in [1, 2, 3]): # jan - mar
                energiledd = 32.09
            else: # apr - dec
                energiledd = 40.75
        else: # day
            if (month in [1, 2, 3]): # jan - mar
                energiledd = 39.59
            else:
                energiledd = 48.25 # apr - dec
        return energiledd/100
    
    def __nettleie_kapasitetsledd(self, demand_array):
        previous_index = 0
        daymax = 0
        daymax_list = []
        series_list = []
        cost_per_hour = 0
        for index, value in enumerate(demand_array):
            if value > daymax:
                daymax = value
            if index % 24 == 23:
                daymax_list.append(daymax)
                daymax = 0
            if index in [744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016, 8759]:
                daymax_list = np.sort(daymax_list)[::-1]
                average_max_value = np.mean(daymax_list[0:3])
                if 0 < average_max_value <= 2:
                    cost = 120
                elif 2 < average_max_value <= 5:
                    cost = 190
                elif 5 < average_max_value <= 10:
                    cost = 305
                elif 10 < average_max_value <= 15:
                    cost = 420
                elif 15 < average_max_value <= 20:
                    cost = 535
                elif 20 < average_max_value <= 25:
                    cost = 650
                elif 25 < average_max_value <= 50:
                    cost = 1225
                elif 50 < average_max_value <= 75:
                    cost = 1800
                elif 75 < average_max_value <= 100:
                    cost = 2375
                elif average_max_value > 100:
                    cost = 4750
                cost_per_hour = cost/(index-previous_index)
                if index == 8759:
                    index = 8760
                daymax_list = []
                previous_index = index
            series_list.append(cost_per_hour)
        return series_list    
    
    def calculate_el_cost(self, demand_array):
        cost_1 = demand_array * self.elprice # energiledd og spotpris
        cost_2 = self.__nettleie_kapasitetsledd(demand_array = demand_array)
        return (cost_1 + cost_2)*1.25

    def __adjust_elprice(self):
        #self.elprice = st.number_input("Velg strømpris [kr/kWh]", min_value = 1.0, value = 2.0, max_value = 5.0, step = 0.1)
        selected_el_option = st.selectbox(f"Strømpris inkl. nettleie, avgifter og mva i {self.elprice_region}", options=["Strømpris i 2023", "Strømpris i 2022", "Strømpris i 2021", "Flat strømpris: 1.1 kr/kWh", "Flat strømpris: 1.5 kr/kWh", "Flat strømpris: 2.0 kr/kWh", "Flat strømpris: 2.5 kr/kWh", "Flat strømpris: 3.0 kr/kWh"], index = 0)
        self.selected_el_option = selected_el_option
        if (selected_el_option == "Strømpris i 2023") or (selected_el_option == "Strømpris i 2022") or (selected_el_option == "Strømpris i 2021"):
            selected_year = selected_el_option.split()[2]
            df = import_spotprice(selected_year = selected_year)
            df['Dato/klokkeslett'] = pd.to_datetime(df['Dato/klokkeslett'], format='%Y-%m-%d Kl. %H-%M')
            df['Energiledd'] = df.apply(self.__nettleie_energiledd, axis=1)
            self.elprice = df[self.ELPRICE_REGIONS_BACK[self.elprice_region]].to_numpy()/1.25 + df['Energiledd'].to_numpy()
        else:
            selected_year = selected_el_option.split()[2]
            self.elprice = float(selected_year)
             
    def __adjust_energymix(self):
        option_list = ['Norsk', 'Norsk-europeisk', 'Europeisk']
        selected = st.selectbox('Strømmiks', options=option_list, index = 1)
        x = {option_list[0] : 19/1000, option_list[1] : 116.9/1000, option_list[2] : 123/1000}
        self.emission_constant_electricity = x[selected]
        self.selected_emission_constant = selected
        
    def __adjust_interest(self):
        self.INTEREST = st.number_input("Lånerente [%]", min_value = 0.0, value = self.INTEREST, max_value = 10.0, step = 0.1)
    
    def __dekningsgrad_calculation(self, dekningsgrad, timeserie):
        if dekningsgrad == 100:
            return timeserie
        timeserie_sortert = np.sort(timeserie)
        timeserie_sum = np.sum(timeserie)
        timeserie_N = len(timeserie)
        startpunkt = timeserie_N // 2
        i = 0
        avvik = 0.0001
        pm = 2 + avvik
        while abs(pm - 1) > avvik:
            cutoff = timeserie_sortert[startpunkt]
            timeserie_tmp = np.where(timeserie > cutoff, cutoff, timeserie)
            beregnet_dekningsgrad = (np.sum(timeserie_tmp) / timeserie_sum) * 100
            pm = beregnet_dekningsgrad / dekningsgrad
            gammelt_startpunkt = startpunkt
            if pm < 1:
                startpunkt = startpunkt + timeserie_N // 2 ** (i + 2) - 1
            else:
                startpunkt = startpunkt - timeserie_N // 2 ** (i + 2) - 1
            if startpunkt == gammelt_startpunkt:
                break
            i += 1
            if i > 13:
                break
        return timeserie_tmp
    
    def __adjust_heat_pump_size(self):
        #dekningsgrad = st.number_input("Energidekningsgrad [%]", value=100, min_value = 90, max_value = 100)
        dekningsgrad = 100
        thermal_demand = self.dhw_demand + self.space_heating_demand
        heat_pump_series = self.__dekningsgrad_calculation(dekningsgrad = dekningsgrad, timeserie = thermal_demand)
        heat_pump_size = np.max(heat_pump_series)
        self.heat_pump_size = self.__rounding_to_int(heat_pump_size)
        #self.heat_pump_size = st.number_input("Varmepumpestørrelse [kW]", value=self.__rounding_to_int(heat_pump_size), min_value = self.__rounding_to_int(np.max(thermal_demand)*0.4), max_value = self.__rounding_to_int(np.max(thermal_demand)))
        
    def borehole_calculation(self):
        # energy
        thermal_demand = self.dhw_demand + self.space_heating_demand
        self.heat_pump_series = np.where(thermal_demand > self.heat_pump_size, self.heat_pump_size, thermal_demand)
        self.delivered_from_wells_series = ((self.heat_pump_series - self.dhw_demand) * (1 - 1/self.COMBINED_COP)) + ((self.dhw_demand) * (1 - 1/self.DHW_COP))
        self.compressor_series = self.heat_pump_series - self.delivered_from_wells_series
        self.peak_series = thermal_demand - self.heat_pump_series
        # energy for calculation
        heat_pump_series_for_calculation = self.__dekningsgrad_calculation(dekningsgrad = 99, timeserie = thermal_demand)
        delivered_from_wells_series_for_calculation = ((heat_pump_series_for_calculation - self.dhw_demand) * (1 - 1/self.COMBINED_COP)) + ((self.dhw_demand) * (1 - 1/self.DHW_COP))
        compressor_series_for_calculation = heat_pump_series_for_calculation - delivered_from_wells_series_for_calculation
        peak_series_for_calculation = thermal_demand - heat_pump_series_for_calculation
        # ghetool
        if self.average_temperature < 5:
            ground_temperature = 5
        elif self.average_temperature > 7:
            ground_temperature = 7
        else:
            ground_temperature = self.average_temperature
        data = GroundData(k_s = self.THERMAL_CONDUCTIVITY, T_g = ground_temperature, R_b = 0.10, flux = 0.04)
        borefield = Borefield(simulation_period = self.BOREHOLE_SIMULATION_YEARS)
        borefield.set_ground_parameters(data) 
        borefield.set_hourly_heating_load(heating_load = delivered_from_wells_series_for_calculation)
        borefield.set_hourly_cooling_load(np.zeros(8760))        
        borefield.set_max_ground_temperature(16)
        borefield.set_min_ground_temperature(self.MINIMUM_TEMPERATURE)
        i = 0
        self.borehole_depth = self.MAXIMUM_DEPTH + 1
        self.progress_bar.progress(50, "Gjør beregninger...")
        while self.borehole_depth >= self.MAXIMUM_DEPTH:
            borefield_gt = gt.boreholes.rectangle_field(N_1 = 1, N_2 = i + 1, B_1 = 15, B_2 = 15, H = 100, D = self.BOREHOLE_BURIED_DEPTH, r_b = self.BOREHOLE_RADIUS)
            borefield.set_borefield(borefield_gt)         
            self.borehole_depth = borefield.size(L4_sizing=True, use_constant_Tg = False) + self.GROUNDWATER_TABLE
            #self.borehole_temperature_arr = borefield.results_peak_heating
            self.number_of_boreholes = borefield.number_of_boreholes
            self.kWh_per_meter = np.sum((self.delivered_from_wells_series)/(self.borehole_depth * self.number_of_boreholes))
            self.W_per_meter = np.max((self.delivered_from_wells_series))/(self.borehole_depth * self.number_of_boreholes) * 1000
            i = i + 1
        new_depth = borefield.size(L3_sizing=True, use_constant_Tg = False) + self.GROUNDWATER_TABLE # må være der for å unngå print
        self.borehole_temperature_arr = borefield.results_peak_heating
            
    def __render_svg_metric(self, svg, text, result):
        """Renders the given svg string."""
        b64 = base64.b64encode(svg.encode('utf-8')).decode("utf-8")
        html = f'<medium> {text} </medium> <br> <img src="data:image/svg+xml;base64,%s"/> <font size="+5">  {result} </font>' % b64
        st.write(html, unsafe_allow_html=True)

    def __custom_sort_array(self, array):
        df = pd.DataFrame(array, columns=['kW'])
        date_index = pd.date_range(start='2023-01-01', periods=len(array), freq='H')
        df.set_index(date_index, inplace=True)
        sorted_df_first = df['2023-07-01':'2023-12-31']
        sorted_df_first.sort_index(inplace=True)
        sorted_df_second = df['2023-01-01':'2023-06-30']
        sorted_df_second.sort_index(inplace=True)
        merged_array = np.concatenate((sorted_df_first.to_numpy(), sorted_df_second.to_numpy()), axis=0).flatten()
        return merged_array
                
    def __plot_gshp_delivered(self):
        y_arr_1 = self.compressor_series
        y_arr_2 = self.delivered_from_wells_series
        y_arr_3 = self.peak_series
        #--
        y_arr_1 = self.__custom_sort_array(array = y_arr_1)
        y_arr_2 = self.__custom_sort_array(array = y_arr_2)
        y_arr_3 = self.__custom_sort_array(array = y_arr_3)
        #--
        x_arr = np.array(range(0, len(y_arr_2)))
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=x_arr,
                y=y_arr_1,
                hoverinfo='skip',
                stackgroup="one",
                fill="tonexty",
                line=dict(width=0, color="#1d3c34"),
                name=f"Strøm til<br>varmepumpe:<br>{self.__rounding_to_int_demand(np.sum(y_arr_1), rounding=-2):,} kWh/år".replace(
                    ",", " "
                ))
        )
        fig.add_trace(
            go.Scatter(
                x=x_arr,
                y=y_arr_2,
                hoverinfo='skip',
                stackgroup="one",
                fill="tonexty",
                line=dict(width=0, color="#48a23f"),
                name=f"Fra brønner:<br>{self.__rounding_to_int_demand(np.sum(y_arr_2 + y_arr_3), rounding=-2):,} kWh/år".replace(
                    ",", " "
                ))
        )
        #fig.add_trace(
        #    go.Scatter(
        #        x=x_arr,
        #        y=y_arr_3,
        #        hoverinfo='skip',
        #        stackgroup="one",
        #        fill="tonexty",
        #        line=dict(width=0, color="#e1b1b5"),
        #        name=f"Spisslast:<br>{self.__rounding_to_int(np.sum(y_arr_3)):,} kWh/år".replace(
        #            ",", " "
        #        ))
        #)
        fig["data"][0]["showlegend"] = True
        fig.update_layout(
        margin=dict(l=50,r=50,b=10,t=10,pad=0),
        yaxis_title="Effekt [kW]",
        legend_title_font=dict(size=16),
        legend_font=dict(size=16),
        plot_bgcolor="white",
        legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0)"),
        barmode="stack",
        xaxis = dict(
                tickmode = 'array',
                tickvals = [0, 24 * (31), 24 * (31 + 28), 24 * (31 + 28 + 31), 24 * (31 + 28 + 31 + 30), 24 * (31 + 28 + 31 + 30 + 31), 24 * (31 + 28 + 31 + 30 + 31 + 30), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31 + 31), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31 + 30), 24 * (31 + 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31 + 30 + 31)],
                ticktext = ["1.jul", "", "1.sep", "", "1.nov", "", "1.jan", "", "1.mar", "", "1.mai", "", "1.jul"]
                )
                )
        fig.update_xaxes(
            range=[0, 8760],
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_yaxes(
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        return fig
    
    def __plot_borehole_temperature(self):
        y_array = self.borehole_temperature_arr
        x_array = np.array(range(0, len(self.borehole_temperature_arr)))
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=x_array,
                y=y_array,
                hoverinfo='skip',
                mode='lines',
                line=dict(width=1.0, color="#1d3c34"),
            ))
           
        fig.update_layout(legend=dict(itemsizing='constant'))
        fig.update_layout(
            margin=dict(l=50,r=50,b=10,t=10,pad=0),
            yaxis_title="Gjennomsnittlig kollektorvæsketemperatur [°C]",
            plot_bgcolor="white",
            barmode="stack",
            xaxis = dict(
                tickmode = 'array',
                tickvals = [12 * 5, 12 * 10, 12 * 15, 12 * 20, 12 * 25, 12 * 30],
                ticktext = ["År 5", "År 10", "År 15", "År 20", "År 25", "År 30"]
                ))
        fig.update_xaxes(
            range=[0, 12 * 31],
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        fig.update_yaxes(
            ticks="outside",
            linecolor="black",
            gridcolor="lightgrey",
            gridwidth=0.3,
        )
        return fig
    
    def __round_up_to_nearest_10(self, number):
        return math.ceil(number / 10) * 10

    def __rounding_to_int(self, number, ):
        return math.ceil(round(number, 1))
    
    def __rounding_to_int_demand(self, number, rounding=-2):
        return math.ceil(round(number, rounding))
    
    def __rounding_to_float(self, number):
        return (round(number, 1))
    
    def __rounding_costs_to_int(self, number):
        return math.ceil(round(number, -3))
    
    def __rounding_cost_plot_to_int(self, number):
        return math.ceil(round(number, -2))
    
    def sizing_results(self):
        with st.container():
            st.write("**Energibrønn og varmepumpe**")
            if self.number_of_boreholes == 1:
                well_description_text = "brønn"
            else:
                well_description_text = "brønner"
            column_1, column_2 = st.columns(2)
            with column_1:
                svg = """<svg width="27" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="505" y="120" width="27" height="26"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-505 -120)"><path d="M18.6875 10.8333C20.9312 10.8333 22.75 12.6522 22.75 14.8958 22.75 17.1395 20.9312 18.9583 18.6875 18.9583L2.97917 18.9583C2.82959 18.9583 2.70833 19.0796 2.70833 19.2292 2.70833 19.3787 2.82959 19.5 2.97917 19.5L18.6875 19.5C21.2303 19.5 23.2917 17.4386 23.2917 14.8958 23.2917 12.353 21.2303 10.2917 18.6875 10.2917L3.63946 10.2917C3.63797 10.2916 3.63678 10.2904 3.63678 10.2889 3.6368 10.2882 3.63708 10.2875 3.63756 10.2871L7.23315 6.69148C7.33706 6.58388 7.33409 6.41244 7.22648 6.30852 7.12154 6.20715 6.95514 6.20715 6.85019 6.30852L2.78769 10.371C2.68196 10.4768 2.68196 10.6482 2.78769 10.754L6.85019 14.8165C6.95779 14.9204 7.12923 14.9174 7.23315 14.8098 7.33452 14.7049 7.33452 14.5385 7.23315 14.4335L3.63756 10.8379C3.63651 10.8369 3.63653 10.8351 3.63759 10.8341 3.6381 10.8336 3.63875 10.8333 3.63946 10.8333Z" stroke="#005173" stroke-width="0.270833" fill="#005173" transform="matrix(6.12323e-17 1 -1.03846 6.35874e-17 532 120)"/></g></svg>"""
                total_meters = self.__round_up_to_nearest_10(self.number_of_boreholes * self.borehole_depth)
                if self.number_of_boreholes > 1:
                    self.borehole_depth = round((total_meters/self.number_of_boreholes) / 5) * 5
                    self.__render_svg_metric(svg, "Brønndybde", f"{self.number_of_boreholes} {well_description_text} á {self.__rounding_to_int(self.borehole_depth)} m")
                else:
                    self.borehole_depth = total_meters
                    self.__render_svg_metric(svg, "Brønndybde", f"{self.number_of_boreholes} {well_description_text} á {self.__rounding_to_int(self.borehole_depth)} m")
            with column_2:
                if self.__rounding_to_int(np.max(self.peak_series)) != 0:
                    svg = """<svg width="27" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="395" y="267" width="31" height="26"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-395 -267)"><path d="M24.3005 0.230906 28.8817 0.230906 28.8817 25.7691 24.3005 25.7691Z" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 2.48455 1.40391 25.5936 6.41918 25.5936 6.41918 2.48455C4.70124 1.49627 3.02948 1.44085 1.40391 2.48455Z" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 25.7691 1.23766 25.7691" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 0.230906 6.59467 0.230906 6.59467 25.7691" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 17.6874 6.59467 17.6874" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 8.33108 6.59467 8.33108" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.71652 12.4874 10.1691 12.4874 10.1691 14.0114 11.222 14.7133 11.222 16.108 10.2153 16.8007 9.71652 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.72575 12.4874 9.26394 12.4874 9.26394 14.0114 8.22025 14.7133 8.22025 16.108 9.21776 16.8007 9.72575 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 12.4874 14.7226 12.4874 14.7226 14.0114 15.7663 14.7133 15.7663 16.108 14.7687 16.8007 14.27 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 12.4874 13.8174 12.4874 13.8174 14.0114 12.7645 14.7133 12.7645 16.108 13.7712 16.8007 14.27 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 5.90195 0.230906 5.90195 0.230906 10.9542 1.40391 10.9542" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 13.0046 0.230906 13.0046 0.230906 25.0025 1.40391 25.0025" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M28.0412 4.58117 25.2611 4.58117 25.2611 2.73393 25.2611 2.10586 28.0412 2.10586 28.0412 4.58117Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 2.73393 28.0412 2.73393" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 3.34352 28.0412 3.34352" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 3.95311 28.0412 3.95311" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.71652 20.6799 10.1691 20.6799 10.1691 22.2131 11.222 22.9059 11.222 24.3005 10.2153 25.0025 9.71652 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.72575 20.6799 9.26394 20.6799 9.26394 22.2131 8.22025 22.9059 8.22025 24.3005 9.21776 25.0025 9.72575 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 20.6799 14.7226 20.6799 14.7226 22.2131 15.7663 22.9059 15.7663 24.3005 14.7687 25.0025 14.27 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 20.6799 13.8174 20.6799 13.8174 22.2131 12.7645 22.9059 12.7645 24.3005 13.7712 25.0025 14.27 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.0149 1.05293 23.4139 1.05293 23.4139 7.56448 20.0149 7.56448Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M17.9552 13.0046 23.4046 13.0046 23.4046 15.5538 17.9552 15.5538Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M19.0913 11.6931C19.0913 11.9073 18.9176 12.081 18.7034 12.081 18.4891 12.081 18.3155 11.9073 18.3155 11.6931 18.3155 11.4788 18.4891 11.3052 18.7034 11.3052 18.9176 11.3052 19.0913 11.4788 19.0913 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M18.7034 13.0046 18.7034 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.4028 11.6931C20.4028 11.9073 20.2292 12.081 20.0149 12.081 19.8007 12.081 19.627 11.9073 19.627 11.6931 19.627 11.4788 19.8007 11.3052 20.0149 11.3052 20.2292 11.3052 20.4028 11.4788 20.4028 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.0149 13.0046 20.0149 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M21.7421 11.6931C21.7421 11.9073 21.5684 12.081 21.3542 12.081 21.1399 12.081 20.9663 11.9073 20.9663 11.6931 20.9663 11.4788 21.1399 11.3052 21.3542 11.3052 21.5684 11.3052 21.7421 11.4788 21.7421 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M21.3542 13.0046 21.3542 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M23.0536 11.6931C23.0536 11.9073 22.88 12.081 22.6657 12.081 22.4515 12.081 22.2778 11.9073 22.2778 11.6931 22.2778 11.4788 22.4515 11.3052 22.6657 11.3052 22.88 11.3052 23.0536 11.4788 23.0536 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M22.6657 13.0046 22.6657 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/></g></svg>"""
                    self.__render_svg_metric(svg, "Varmepumpestørrelse", f"{self.heat_pump_size-1} – {self.heat_pump_size+1} kW")
                else:
                    svg = """<svg width="27" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="395" y="267" width="31" height="26"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-395 -267)"><path d="M24.3005 0.230906 28.8817 0.230906 28.8817 25.7691 24.3005 25.7691Z" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 2.48455 1.40391 25.5936 6.41918 25.5936 6.41918 2.48455C4.70124 1.49627 3.02948 1.44085 1.40391 2.48455Z" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 25.7691 1.23766 25.7691" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 0.230906 6.59467 0.230906 6.59467 25.7691" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 17.6874 6.59467 17.6874" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M24.3005 8.33108 6.59467 8.33108" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-miterlimit="10" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.71652 12.4874 10.1691 12.4874 10.1691 14.0114 11.222 14.7133 11.222 16.108 10.2153 16.8007 9.71652 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.72575 12.4874 9.26394 12.4874 9.26394 14.0114 8.22025 14.7133 8.22025 16.108 9.21776 16.8007 9.72575 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 12.4874 14.7226 12.4874 14.7226 14.0114 15.7663 14.7133 15.7663 16.108 14.7687 16.8007 14.27 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 12.4874 13.8174 12.4874 13.8174 14.0114 12.7645 14.7133 12.7645 16.108 13.7712 16.8007 14.27 16.8007" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 5.90195 0.230906 5.90195 0.230906 10.9542 1.40391 10.9542" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M1.40391 13.0046 0.230906 13.0046 0.230906 25.0025 1.40391 25.0025" stroke="#005173" stroke-width="0.461812" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M28.0412 4.58117 25.2611 4.58117 25.2611 2.73393 25.2611 2.10586 28.0412 2.10586 28.0412 4.58117Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 2.73393 28.0412 2.73393" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 3.34352 28.0412 3.34352" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M25.4366 3.95311 28.0412 3.95311" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.71652 20.6799 10.1691 20.6799 10.1691 22.2131 11.222 22.9059 11.222 24.3005 10.2153 25.0025 9.71652 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M9.72575 20.6799 9.26394 20.6799 9.26394 22.2131 8.22025 22.9059 8.22025 24.3005 9.21776 25.0025 9.72575 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 20.6799 14.7226 20.6799 14.7226 22.2131 15.7663 22.9059 15.7663 24.3005 14.7687 25.0025 14.27 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M14.27 20.6799 13.8174 20.6799 13.8174 22.2131 12.7645 22.9059 12.7645 24.3005 13.7712 25.0025 14.27 25.0025" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.0149 1.05293 23.4139 1.05293 23.4139 7.56448 20.0149 7.56448Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M17.9552 13.0046 23.4046 13.0046 23.4046 15.5538 17.9552 15.5538Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M19.0913 11.6931C19.0913 11.9073 18.9176 12.081 18.7034 12.081 18.4891 12.081 18.3155 11.9073 18.3155 11.6931 18.3155 11.4788 18.4891 11.3052 18.7034 11.3052 18.9176 11.3052 19.0913 11.4788 19.0913 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M18.7034 13.0046 18.7034 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.4028 11.6931C20.4028 11.9073 20.2292 12.081 20.0149 12.081 19.8007 12.081 19.627 11.9073 19.627 11.6931 19.627 11.4788 19.8007 11.3052 20.0149 11.3052 20.2292 11.3052 20.4028 11.4788 20.4028 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M20.0149 13.0046 20.0149 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M21.7421 11.6931C21.7421 11.9073 21.5684 12.081 21.3542 12.081 21.1399 12.081 20.9663 11.9073 20.9663 11.6931 20.9663 11.4788 21.1399 11.3052 21.3542 11.3052 21.5684 11.3052 21.7421 11.4788 21.7421 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M21.3542 13.0046 21.3542 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M23.0536 11.6931C23.0536 11.9073 22.88 12.081 22.6657 12.081 22.4515 12.081 22.2778 11.9073 22.2778 11.6931 22.2778 11.4788 22.4515 11.3052 22.6657 11.3052 22.88 11.3052 23.0536 11.4788 23.0536 11.6931Z" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1.04327 0 0 1 395.314 267)"/><path d="M22.6657 13.0046 22.6657 12.081" stroke="#005173" stroke-width="0.230906" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1.04327 0 0 1 395.314 267)"/></g></svg>"""
                    self.__render_svg_metric(svg, "Varmepumpestørrelse", f"{self.heat_pump_size-1} – {self.heat_pump_size+1} kW")
            
            with st.expander("Mer om brønndybde og varmepumpestørrelse"):
                st.write(""" Vi har gjort en forenklet beregning for å dimensjonere et 
                         bergvarmeanlegg med energibrønn og varmepumpe for din bolig. 
                         Dybde for energibrønn og størrelse på varmepumpe er beregnet 
                         ut fra estimert årlig varmebehov.""")

#                st.write(""" Vi har gjort en forenklet beregning for å dimensjonere et bergvarmeanlegg med 
#                energibrønn og varmepumpe for din bolig. Dybde på energibrønn og størrelse på varmepumpe 
#                beregnes ut ifra et anslått oppvarmingsbehov for boligen din og antakelser om 
#                egenskapene til berggrunnen der du bor.""")
                st.plotly_chart(figure_or_data = self.__plot_gshp_delivered(), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
                #st.write(f""" Dimensjonerende varmeeffektbehov er {self.dut_effect} kW. Med en varmepumpe på {self.heat_pump_size} kW blir effektdekningsgraden {self.__rounding_to_int((self.heat_pump_size/self.dut_effect) * 100)} %.""")
#                st.write(f""" Hvis uttaket av varme fra energibrønnen ikke er balansert med varmetilførselen i grunnen, 
#                        vil temperaturen på bergvarmesystemet synke og energieffektiviteten minke. Det er derfor viktig at energibrønnen er tilstrekkelig dyp
#                        til å kunne balansere varmeuttaket. """)
                if self.number_of_boreholes > 1:
                    energy_well_text = "energibrønnene"
                else:
                    energy_well_text = "energibrønnen"
                st.write(f""" Det er viktig at {energy_well_text} er dyp nok til at temperaturen i {energy_well_text} holder seg jevn over tid. 
                         Den varmen som varmepumpen henter ut fra {energy_well_text}, må balanseres med varme som naturlig tilføres {energy_well_text} fra grunnen rundt den.""")
                
#                st.write(f"""Den innledende beregningen viser at {energy_well_text} kan levere ca. 
#                         {self.__rounding_to_int(self.kWh_per_meter)} kWh/(m∙år) og {self.__rounding_to_int(self.W_per_meter)} W/m for at 
#                         positiv temperatur i grunnen opprettholdes gjennom anleggets levetid. """)
                  
                #st.plotly_chart(figure_or_data = self.__plot_borehole_temperature(), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
                if self.number_of_boreholes > 1:
                    st.info(f"🛈 Det bør være minimum 15 meter avstand mellom brønnene. Dersom de plasseres nærmere vil ytelsen til brønnene bli dårligere.")
                st.warning("""**⚠ Før du kan installere bergvarme, må entreprenøren gjøre en grundigere beregning. 
                Den må baseres på reelt oppvarmings- og kjølebehov, en mer nøyaktig vurdering av grunnforholdene, 
                inkludert berggrunnens termiske egenskaper, og simuleringer av temperaturen i energibrønnen.**""")
        
    def environmental_results(self):
        with st.container():
            st.write("**Strømsparing og utslippskutt**")
            c1, c2 = st.columns(2)
            with c1:
                svg = """ <svg width="13" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="614" y="84" width="13" height="26"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-614 -84)"><path d="M614.386 99.81 624.228 84.3312C624.464 83.9607 625.036 84.2358 624.89 84.6456L621.224 95.1164C621.14 95.3522 621.32 95.5992 621.572 95.5992L626.3 95.5992C626.603 95.5992 626.777 95.9417 626.597 96.1831L616.458 109.691C616.194 110.039 615.644 109.725 615.823 109.326L619.725 100.456C619.838 100.203 619.63 99.9223 619.355 99.9447L614.74 100.36C614.437 100.388 614.229 100.057 614.392 99.7987Z" stroke="#005173" stroke-width="0.308789" stroke-linecap="round" stroke-miterlimit="10" fill="#FFF"/></g></svg>"""
                self.__render_svg_metric(svg, "Spart strøm fra strømnettet", f"{self.__rounding_to_int_demand(np.sum(self.delivered_from_wells_series)):,} kWh/år".replace(',', ' '))
            with c2:
                svg = """ <svg width="26" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="458" y="120" width="26" height="26"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-458 -120)"><path d="M480.21 137.875 480.21 135.438 472.356 129.885 472.356 124.604C472.356 123.548 471.814 122.167 471.001 122.167 470.216 122.167 469.647 123.548 469.647 124.604L469.647 129.885 461.793 135.438 461.793 137.875 469.647 133.948 469.647 139.852 466.939 142.208 466.939 143.833 471.001 142.208 475.064 143.833 475.064 142.208 472.356 139.852 472.356 133.948ZM472 140.261 474.522 142.455 474.522 143.033 471.203 141.706 471.001 141.624 470.8 141.706 467.481 143.033 467.481 142.455 470.003 140.261 470.189 140.099 470.189 133.072 469.403 133.463 462.335 136.999 462.335 135.718 469.96 130.328 470.189 130.166 470.189 124.604C470.189 123.645 470.703 122.708 471.001 122.708 471.341 122.708 471.814 123.664 471.814 124.604L471.814 130.166 472.043 130.328 479.668 135.718 479.668 136.999 472.598 133.463 471.814 133.072 471.814 140.099Z" stroke="#005173" stroke-width="0.270833"/></g></svg>"""
                self.__render_svg_metric(svg, f"Utslippskutt etter {self.BOREHOLE_SIMULATION_YEARS} år", f"{self.emission_savings_flights:,} sparte flyreiser".replace(',', ' '))
            with st.expander("Mer om strømsparing og utslippskutt"):
                st.write(f""" Vi har beregnet hvor mye strøm bergvarme vil spare i din bolig sammenlignet med å bruke elektrisk oppvarming."""
                         + """ I den kaldeste timen om vinteren vil anlegget spare""" + f""" {round(np.max(self.delivered_from_wells_series),1)} kWh """.replace(".", ",") + """strøm fra strømnettet. """ +
                f"""Figurene viser at du sparer {self.__rounding_to_int_demand(np.sum(self.delivered_from_wells_series)):,} kWh i året med bergvarme. 
                Hvis vi tar utgangspunkt i en {self.selected_emission_constant.lower()} strømmiks
                vil du i løpet av {self.BOREHOLE_SIMULATION_YEARS} år spare ca. {self.emission_savings} tonn CO\u2082. Dette tilsvarer **{self.emission_savings_flights} flyreiser** tur-retur Oslo - Trondheim. """.replace(',', ' '))

                st.write()
                self.__plot_environmental()

    def cost_results(self):
        def __show_metrics(investment, short_term_savings, long_term_savings, investment_unit = "kr", short_term_savings_unit = "kr/år", long_term_savings_unit = "kr", investment_text = "Estimert<br>investeringskostnad"):
            column_1, column_2, column_3 = st.columns(3)
            with column_1:
                svg = """ <svg width="26" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="369" y="79" width="26" height="27"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-369 -79)"><path d="M25.4011 12.9974C25.4011 19.8478 19.8478 25.4011 12.9974 25.4011 6.14699 25.4011 0.593654 19.8478 0.593654 12.9974 0.593654 6.14699 6.14699 0.593654 12.9974 0.593654 19.8478 0.593654 25.4011 6.14699 25.4011 12.9974Z" stroke="#005173" stroke-width="0.757136" stroke-miterlimit="10" fill="#fff" transform="matrix(1 0 0 1.03846 369 79)"/><path d="M16.7905 6.98727 11.8101 19.0075 11.6997 19.0075 9.20954 12.9974" stroke="#005173" stroke-width="0.757136" stroke-linejoin="round" fill="none" transform="matrix(1 0 0 1.03846 369 79)"/></g></svg>"""
                self.__render_svg_metric(svg, f"{investment_text}", f"{self.__rounding_costs_to_int(investment):,} {investment_unit}".replace(',', ' '))
            with column_2:
                svg = """ <svg width="29" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="323" y="79" width="29" height="27"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-323 -79)"><path d="M102.292 91.6051C102.292 91.6051 102.831 89.8359 111.221 89.8359 120.549 89.8359 120.01 91.6051 120.01 91.6051L120.01 107.574C120.01 107.574 120.523 109.349 111.221 109.349 102.831 109.349 102.292 107.574 102.292 107.574Z" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 94.7128C102.292 94.7128 102.831 96.4872 111.221 96.4872 120.549 96.4872 120.01 94.7128 120.01 94.7128" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 97.9487C102.292 97.9487 102.831 99.718 111.221 99.718 120.549 99.718 120 97.9487 120 97.9487" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 101.19C102.292 101.19 102.831 102.964 111.221 102.964 120.549 102.964 120.01 101.19 120.01 101.19" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 104.385C102.292 104.385 102.831 106.154 111.221 106.154 120.549 106.154 120.01 104.385 120.01 104.385" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M120 91.6051C120 91.6051 120.513 93.3795 111.21 93.3795 102.821 93.3795 102.282 91.6051 102.282 91.6051" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M19.0769 16.7436C19.0769 21.9407 14.8638 26.1538 9.66667 26.1538 4.46953 26.1538 0.25641 21.9407 0.25641 16.7436 0.25641 11.5465 4.46953 7.33333 9.66667 7.33333 14.8638 7.33333 19.0769 11.5464 19.0769 16.7436Z" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 323 79.0234)"/><path d="M9.66667 11.6 11.4564 15.9231 15.1487 14.5744 14.4513 19.3231 4.88205 19.3231 4.18462 14.5744 7.87692 15.9231 9.66667 11.6Z" stroke="#005173" stroke-width="0.512821" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1 0 0 1.02056 323 79.0234)"/><path d="M4.86667 20.3846 14.5231 20.3846" stroke="#005173" stroke-width="0.512821" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1 0 0 1.02056 323 79.0234)"/></g></svg>"""
                self.__render_svg_metric(svg, f"Reduserte utgifter<br>til oppvarming", f"{self.__rounding_costs_to_int(short_term_savings):,} {short_term_savings_unit}".replace(',', ' ')) 
            with column_3:
                svg = """ <svg width="29" height="35" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" overflow="hidden"><defs><clipPath id="clip0"><rect x="323" y="79" width="29" height="27"/></clipPath></defs><g clip-path="url(#clip0)" transform="translate(-323 -79)"><path d="M102.292 91.6051C102.292 91.6051 102.831 89.8359 111.221 89.8359 120.549 89.8359 120.01 91.6051 120.01 91.6051L120.01 107.574C120.01 107.574 120.523 109.349 111.221 109.349 102.831 109.349 102.292 107.574 102.292 107.574Z" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 94.7128C102.292 94.7128 102.831 96.4872 111.221 96.4872 120.549 96.4872 120.01 94.7128 120.01 94.7128" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 97.9487C102.292 97.9487 102.831 99.718 111.221 99.718 120.549 99.718 120 97.9487 120 97.9487" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 101.19C102.292 101.19 102.831 102.964 111.221 102.964 120.549 102.964 120.01 101.19 120.01 101.19" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M102.292 104.385C102.292 104.385 102.831 106.154 111.221 106.154 120.549 106.154 120.01 104.385 120.01 104.385" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M120 91.6051C120 91.6051 120.513 93.3795 111.21 93.3795 102.821 93.3795 102.282 91.6051 102.282 91.6051" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 231.728 -12.3976)"/><path d="M19.0769 16.7436C19.0769 21.9407 14.8638 26.1538 9.66667 26.1538 4.46953 26.1538 0.25641 21.9407 0.25641 16.7436 0.25641 11.5465 4.46953 7.33333 9.66667 7.33333 14.8638 7.33333 19.0769 11.5464 19.0769 16.7436Z" stroke="#005173" stroke-width="0.512821" stroke-miterlimit="10" fill="#FFF" transform="matrix(1 0 0 1.02056 323 79.0234)"/><path d="M9.66667 11.6 11.4564 15.9231 15.1487 14.5744 14.4513 19.3231 4.88205 19.3231 4.18462 14.5744 7.87692 15.9231 9.66667 11.6Z" stroke="#005173" stroke-width="0.512821" stroke-linecap="round" stroke-linejoin="round" fill="#FFF" transform="matrix(1 0 0 1.02056 323 79.0234)"/><path d="M4.86667 20.3846 14.5231 20.3846" stroke="#005173" stroke-width="0.512821" stroke-linecap="round" stroke-linejoin="round" fill="none" transform="matrix(1 0 0 1.02056 323 79.0234)"/></g></svg>"""
                self.__render_svg_metric(svg, f"Samlet besparelse<br>etter {self.BOREHOLE_SIMULATION_YEARS} år", f"{self.__rounding_costs_to_int(long_term_savings):,} {long_term_savings_unit}".replace(',', ' ')) 
           
        with st.container():
            st.write("**Tilbakebetalingstid**")
            tab1, tab2 = st.tabs(["Direktekjøp", "Lånefinansiert"])
            with tab1:
                # direktekjøp
                __show_metrics(investment = self.investment_cost, short_term_savings = self.short_term_investment, long_term_savings = self.long_term_investment)
                with st.expander("Mer om tilbakebetalingstid med bergvarme"): 
                    
                    st.write(""" Estimert investeringskostnad dekker et komplett bergvarmeanlegg, 
                             inkludert energibrønn, varmepumpe og installasjon. Vi har antatt at kostnadene fordeler seg slik: """)
                    st.write(f"- • Energibrønn: {self.__rounding_costs_to_int(self.geoenergy_investment_cost):,} kr".replace(",", " "))
                    st.write(f"- • Bergvarmepumpe: {self.__rounding_costs_to_int(self.heat_pump_cost):,} kr".replace(",", " "))
                    

                    if self.waterborne_heat_cost > 0:
                        st.write(f"- • Vannbåren varme: {self.__rounding_costs_to_int(self.waterborne_heat_cost):,} kr".replace(",", " "))
#                        st.write(f"- • Enovatilskudd: {self.enova_tilskudd:,} kr".replace(",", " "))
#                    else:
#                        st.write(f"- • Enovatilskudd {self.enova_tilskudd:,} kr".replace(",", " "))
                        
                    st.write("")
                    st.write(""" Prisene er inkludert mva. NB! Dette er et anslag basert på priser 
                             fra en spørreundersøkelse blant forhandlere høsten 2023. 
                             Faktiske priser kan variere mye fra sted til sted, og bestemmes av leverandør.""")
                    
                    st.write(f""" Investeringen kvalifiserer for Enovatilskudd - vi estimerer at du får {self.enova_tilskudd:,} kr i støtte.""".replace(",", " "))
                    st.write("")
                    st.markdown(f'<a target="parent" style="background-color: #white;color:black;border: solid 1px #e5e7eb; border-radius: 15px; text-align: center;padding: 16px 24px;min-height: 60px;display: inline-block;box-sizing: border-box;width: 100%;" href="https://www.varmepumpeinfo.no/tilskudd-fra-enova">Bergvarmepumper får tilskudd fra Enova. Les mer her.</a>', unsafe_allow_html=True)     
                    payment_time = math.ceil(-self.investment_cost / ((np.sum(self.geoenergy_operation_cost) - np.sum(self.direct_el_operation_cost))))
                    if payment_time < 30:
                        st.write(f"Grafene under viser at anlegget er nedbetalt etter ca. {payment_time} år.")
                        st.plotly_chart(figure_or_data = self.__plot_costs_investment(), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
#                        st.plotly_chart(figure_or_data = self.__plot_costs_monthly(geoenergy_operation_cost=hour_to_month(self.geoenergy_operation_cost), direct_el_operation_cost=hour_to_month(self.direct_el_operation_cost)), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
                    else:
                        st.warning(f"⚠ Med estimerte investeringskostnader, dagens støtteordninger og {self.selected_el_option.lower()} er bergvarme nedbetalt etter ca. {payment_time} år.")

            with tab2:
                # lån
                if self.short_term_loan > 0:
                    __show_metrics(investment = 0, short_term_savings = self.short_term_loan, long_term_savings = self.long_term_loan, investment_text = "Investeringskostnad (lånefinansiert)")
                    with st.expander("Mer om tilbakebetalingstid med bergvarme"):                       
                        st.write(f""" Mange banker har begynt å tilby billigere boliglån hvis boligen regnes som miljøvennlig; et såkalt grønt boliglån. 
                        En oppgradering til bergvarme kan kvalifisere boligen din til et slikt lån. """)
                        st.write(f""" Grafene under viser årlige kostnader til oppvarming hvis investeringen finansieres 
                        av et grønt lån. """ + f""" Her har vi forutsatt at investeringen nedbetales i 
                        løpet av {self.BOREHOLE_SIMULATION_YEARS} år med effektiv rente på {round(self.INTEREST,2)} %""".replace(".", ",") + ".")
                        st.plotly_chart(figure_or_data = self.__plot_costs_loan(), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
#                        st.plotly_chart(figure_or_data = self.__plot_costs_monthly(geoenergy_operation_cost=hour_to_month(self.geoenergy_operation_cost) + np.full(12, self.loan_cost_monthly), direct_el_operation_cost=hour_to_month(self.direct_el_operation_cost)), use_container_width=True, config = {'displayModeBar': False, 'staticPlot': True})
                else:
                    st.warning("⚠ Lånefinansiering er ikke lønnsomt innenfor varmepumpens levetid.")
            
    def streamlit_results(self):
        st.header("Resultater for din bolig")
        self.sizing_results()
        self.environmental_results()
        self.cost_results()
        #--
        svg = """<svg width="27" height="35" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <rect width="24" height="24" fill="white"></rect> <path d="M9.5 7L14.5 12L9.5 17" stroke="#000000" stroke-linecap="round" stroke-linejoin="round"></path> </g></svg> """
        b64 = base64.b64encode(svg.encode('utf-8')).decode("utf-8")
        html = f'<medium> Du kan endre strømpris og andre forutsetninger ved å trykke på <img src="data:image/svg+xml;base64,%s"/> øverst til venstre. </medium>  <font size="+5">  </font>' % b64
        st.write(html, unsafe_allow_html=True)
        
    def streamlit_hide_fullscreen_view(self):
        hide_img_fs = '''
            <style>
            button[title="View fullscreen"]{
                visibility: hidden;}
            </style>
            '''
        st.markdown(hide_img_fs, unsafe_allow_html=True)
        
    def novap(self):
        st.header("Veien videre")
        st.write(""" Sjekk hvilke entreprenører som kan montere varmepumpe og bore energibrønn hos deg - riktig og trygt! Bruk en entreprenør godkjent av Varmepumpeforeningen. """)
        st.write(""" Vi råder deg også til å:""")
        st.write("- • Få entreprenør til å komme på befaring")
        st.write("- • Vurdere både pris og kvalitet ")
        st.write("- • Skrive kontrakt før arbeidet starter")
        # Til NOVAP
        # Standard Base64 Encoding
        data = {}
        data['antall_borehull'] = self.number_of_boreholes
        data['bronndybde'] = self.borehole_depth
        data['varmepumpe'] = self.heat_pump_size
        data['oppvarmingsbehov'] = self.__rounding_to_int(np.sum(self.dhw_demand + self.space_heating_demand))
        data['varmtvannsbehov'] = self.__rounding_to_int(np.sum(self.dhw_demand))
        data['romoppvarmingsbehov'] = self.__rounding_to_int(np.sum(self.space_heating_demand))
        data['boligareal'] = self.building_area
        data['adresse'] = self.address_name
        data['investeringskostnad'] = self.investment_cost
        json_data = json.dumps(data)      
        encodedBytes = base64.b64encode(json_data.encode("utf-8"))
        encodedStr = str(encodedBytes, "utf-8")
        st.write("")
        st.markdown(f'<a target="parent" style="color: white !important; font-weight:600; font-size: 20px; border-radius: 15px; text-align: center; padding: 1rem; min-height: 60px; display: inline-block; box-sizing: border-box; width: 100%;" href="https://www.varmepumpeinfo.no/forhandler?postnr={self.address_postcode}&adresse={self.address_str}&type=bergvarme&meta={encodedStr}">Sett i gang - finn en seriøs forhandler!</a>', unsafe_allow_html=True)

    def main(self):    
        self.streamlit_hide_fullscreen_view()
        self.streamlit_input_container() # start progress bar
        self.streamlit_calculations()
        # ferdig
        self.progress_bar.progress(100, text="Fullført")
        self.streamlit_results()
        self.novap()
        
if __name__ == '__main__':
    calculator = Calculator()
    calculator.main()