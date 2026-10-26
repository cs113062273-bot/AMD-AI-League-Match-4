# Common organizer base: preserve every lower layer; never squash this final stage.
FROM rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0@sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    APERTURE_MODEL=/models/qwen APERTURE_REQUIRE_GPU=1 APERTURE_BUDGET=24 \
    APERTURE_OUTPUT=/app/output APERTURE_PROFILE=minimal
ARG INSTALL_BROWSER=1
ARG PLAYWRIGHT_DOWNLOAD_HOST
ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX=0
ARG PIP_TRUSTED_HOST
ARG APERTURE_APT_CACHE
ENV APERTURE_BROWSER=${INSTALL_BROWSER}
COPY requirements.txt requirements-model.txt requirements-runtime.lock requirements-browser.lock /app/
COPY scripts/protect_torch.py /app/scripts/protect_torch.py
RUN python3 /app/scripts/protect_torch.py --constraints /tmp/torch-constraints.txt \
 && python3 -m pip install --no-cache-dir --no-deps -c /tmp/torch-constraints.txt -r requirements-runtime.lock \
 && python3 -m pip check \
 && python3 /app/scripts/protect_torch.py --require-rocm
RUN if [ "$INSTALL_BROWSER" = 1 ]; then \
      if [ -n "$APERTURE_APT_CACHE" ]; then \
        sed -i "s|http://archive.ubuntu.com|$APERTURE_APT_CACHE/apt/archive.ubuntu.com|g; s|http://security.ubuntu.com|$APERTURE_APT_CACHE/apt/security.ubuntu.com|g" /etc/apt/sources.list.d/ubuntu.sources; fi; \
      python3 -m pip install --no-cache-dir --no-deps -r requirements-browser.lock \
      && python3 -m playwright install --with-deps --only-shell chromium \
      && python3 -m pip check; fi
COPY models/qwen /models/qwen
COPY agent /app/agent
COPY app.py /app/app.py
COPY LICENSE /app/LICENSE
COPY scripts/gpu_smoke_test.py /app/scripts/gpu_smoke_test.py
COPY scripts/runtime_compat_smoke.py /app/scripts/runtime_compat_smoke.py
COPY scripts/container_inventory.py /app/scripts/container_inventory.py
RUN test -s /models/qwen/model.safetensors.index.json \
 && test -s /models/qwen/aperture-model.json \
 && python3 -m agent.model_assets /models/qwen \
 && mkdir -p /app/output
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s --retries=48 \
 CMD python3 -c "import urllib.request,json; opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); assert json.load(opener.open('http://127.0.0.1:8765/health',timeout=2))['ready']"
CMD ["python3", "/app/app.py", "--serve"]
