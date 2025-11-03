# --- Convert MySQL binary UUID columns if required ---
if uuid_cols:
    import binascii
    for col in uuid_cols:
        if col in mysql_pd.columns:
            mysql_pd[col] = mysql_pd[col].apply(
                lambda x: binascii.hexlify(x).decode("utf-8").lower() if isinstance(x, (bytes, bytearray)) else x
            )
        if col in starrocks_pd.columns:
            starrocks_pd[col] = starrocks_pd[col].str.lower()
