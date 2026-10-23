# Task 4 – Book store data
Cleans the raw store data (`books.yaml`, `users.csv`, `orders.parquet`), resolves duplicate books/users and answers the task questions.

## Run
```bash
pip install -r requirements.txt
python main.py STORE1          # console results
streamlit run app.py           # dashboard
```

## Files

- `main.py` – reading, cleaning, entity resolution and analysis
- `app.py` – Streamlit dashboard (revenue / users / authors tabs)
- `STORE1/` – raw data