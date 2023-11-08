import ee
import pandas as pd
from prophet import Prophet
import streamlit as st
import plotly.express as px

# Earth Engine API 초기화
ee.Initialize()

# GeoJSON 구조를 사용하여 AOI 설정
def create_ee_polygon_from_geojson(gjson):
    coordinates = gjson['geometry']['coordinates']
    aoi = ee.Geometry.Polygon(coordinates)
    return aoi

def calculateRVI(aoi,start_date,end_date):
    # Sentinel-1 ImageCollection 필터링
    sentinel1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
            .filterBounds(aoi) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.eq('instrumentMode', 'IW')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
            .filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))

    # RVI 계산 및 시계열 데이터 생성 함수
    def calculate_rvi(image):
        date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
        vv = image.select('VV')
        vh = image.select('VH')
        rvi = vh.multiply(4).divide(vv.add(vh))
        mean_rvi = rvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=10
        ).get('VH')
        return ee.Feature(None, {'ds': date, 'y': mean_rvi})

    # 시계열 RVI 계산
    time_series_rvi = sentinel1.map(calculate_rvi)

    # 결과를 서버측 객체로 변환 (Python 클라이언트로 가져오기 위함)
    rvi_features = time_series_rvi.getInfo()['features']

    # 결과를 pandas DataFrame으로 변환
    df = pd.DataFrame([feat['properties'] for feat in rvi_features])

    # DataFrame을 'Date' 컬럼에 따라 오름차순으로 정렬
    df = df.sort_values(by='ds')
    return df

def prophet_process(df):
    # Prophet 모델을 초기화하고 학습시킵니다.
    m = Prophet(yearly_seasonality=True,daily_seasonality=True)
    m.fit(df)

    # 미래 날짜 프레임을 만들고 예측을 진행합니다.
    future = m.make_future_dataframe(periods=365)
    forecast = m.predict(future) 

    # 예측 결과를 가져옵니다.
    forecasted_value = forecast.iloc[-1]['yhat']  # 예측된 값을 가져옴
    print(f"Forecasted mean NDVI for the next period: {forecasted_value}")

    # 예측 결과를 데이터프레임에 추가합니다.
    forecast_df = df.append({'ds': future.iloc[-1]['ds'], 'y': forecasted_value}, ignore_index=True)
    return forecast,forecast_df,df,m

import plotly.graph_objs as go
from plotly.subplots import make_subplots

def plotly(df, forecast):
    # Create a Plotly Express figure for both forecast and observed data
    combined_fig = px.line(forecast, x='ds', y='yhat', title='예측')
    
    # Add observed data to the same figure
    combined_fig.add_trace(px.scatter(df, x='ds', y='y', title='관측치', color_discrete_sequence=['red']).data[0])

    # Display the combined figure using st.plotly_chart()
    st.plotly_chart(combined_fig)