# Put app code in /app (adjust "." if your app code is elsewhere)
COPY --chown=appuser:appuser . /app

# If you truly need src at runtime (only if something reads /src explicitly)
COPY --chown=appuser:appuser src/ /src/
