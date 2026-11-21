"""Print the A2AJ schema and a few sample rows."""
import duckdb

con = duckdb.connect()
path = "data/raw/a2aj/NSPC/train.parquet"
for row in con.sql(f"DESCRIBE SELECT * FROM '{path}'").fetchall():
    print(row[0], row[1])
print()
for row in con.sql(
    f"SELECT citation_en, name_en, document_date_en, length(unofficial_text_en) "
    f"FROM '{path}' ORDER BY document_date_en DESC LIMIT 5"
).fetchall():
    print(row)
