import pandas as pd

df1 = pd.read_excel("src/csv/dut.xlsx", sheet_name = "Sheet1")
df2 = pd.read_excel("src/csv/dut.xlsx", sheet_name = "Sheet2")

merged_df = pd.merge(df1, df2, on='Stasjon_ID', how='inner')

df3 = pd.read_excel("src/csv/kommunenr.xlsx")
merged_df = pd.merge(merged_df, df3, on='Kommune', how='inner')
merged_df.to_excel("src/csv/temperaturer_kommuner.xlsx")