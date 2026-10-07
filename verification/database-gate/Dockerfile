FROM mcr.microsoft.com/dotnet/sdk:10.0.100@sha256:c7445f141c04f1a6b454181bd098dcfa606c61ba0bd213d0a702489e5bd4cd71 AS dotnet
WORKDIR /src/verification/database-gate
COPY verification/database-gate/dotnet ./dotnet
COPY verification/database-gate/contracts ./contracts
RUN dotnet restore dotnet --locked-mode --verbosity quiet \
    && dotnet publish dotnet --no-restore -c Release -o /out --verbosity quiet /p:UseAppHost=false

FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv
FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS python
COPY --from=uv /uv /usr/local/bin/uv
COPY artifacts/database-gate/payments /payments
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN uv sync --frozen --project /payments --python /usr/local/bin/python

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
# .NET's host and shared runtime copied from the tested SDK; no build at job execution.
RUN apt-get update && apt-get install -y --no-install-recommends git libicu76 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dotnet /usr/share/dotnet/host /usr/share/dotnet/host
COPY --from=dotnet /usr/share/dotnet/shared /usr/share/dotnet/shared
COPY --from=dotnet /usr/share/dotnet/dotnet /usr/share/dotnet/dotnet
COPY --from=dotnet --chown=10001:10001 /out /gate/dotnet
COPY --from=python --chown=10001:10001 /payments /payments
COPY --chown=10001:10001 verification/database-gate/payments-gate.py verification/database-gate/azure-runner.py /gate/verification/database-gate/
COPY --chown=10001:10001 scripts/report-database-gate.py /gate/scripts/
ARG SOURCE_COMMIT
ARG GATE_SOURCE_HASH
LABEL org.opencontainers.image.source="https://github.com/MichalBoczula/ECommerceStore.Infrastructure" \
      org.opencontainers.image.revision=$SOURCE_COMMIT \
      ecommerce.gate-source-sha256=$GATE_SOURCE_HASH \
      ecommerce.payments-commit="9663df14cb10886a32fa7850d1ca51537a3da009"
ENV PATH="/usr/share/dotnet:${PATH}" DOTNET_ROOT=/usr/share/dotnet PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /gate
USER 10001:10001
ENTRYPOINT ["python", "/gate/verification/database-gate/azure-runner.py"]
