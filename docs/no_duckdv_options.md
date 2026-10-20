import duckdb
import fsspec
import pyarrow.dataset as ds
import pyarrow.fs as pafs

# Small public test file; replace with your actual Parquet URL afterwards.
url = "https://duckdb.org/data/prices.parquet"

# Python handles HTTP access instead of DuckDB's httpfs extension.
http = fsspec.filesystem(
    "http",
    block_size=256 * 1024,
    client_kwargs={"trust_env": True},  # use environment proxy settings
)
filesystem = pafs.PyFileSystem(pafs.FSSpecHandler(http))

remote_data = ds.dataset(
    url,
    filesystem=filesystem,
    format="parquet",
)

con = duckdb.connect(config={
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
})
con.register("remote_data", remote_data)

print(con.execute("SELECT * FROM remote_data LIMIT 5").fetchall())
