# ---- Build Stage ----
    FROM ubuntu:24.04 as builder

    LABEL maintainer="Nikola Whallon <nikola@deepgram.com>"
    
    ENV DEBIAN_FRONTEND=noninteractive
    
    RUN apt-get update && \
        apt-get install -y --no-install-recommends \
            ca-certificates \
            clang \
            curl \
            libpq-dev \
            libssl-dev \
            pkg-config \
            unzip \
            libwebrtc-audio-processing-dev
    
    # Install LibTorch
    ARG LIBTORCH_VER
    ENV LIBTORCH_VER=${LIBTORCH_VER:-2.4.0}
    ARG CUDA_VER
    ENV CUDA_VER=${CUDA_VER:-cu121}
    
    RUN curl -sOL https://download.pytorch.org/libtorch/${CUDA_VER}/libtorch-cxx11-abi-shared-with-deps-${LIBTORCH_VER}%2B${CUDA_VER}.zip && \
        unzip -d /opt/ libtorch*zip && \
        echo "/opt/libtorch/lib" | tee -a /etc/ld.so.conf.d/libtorch.conf && ldconfig
    
    ENV LIBTORCH=/opt/libtorch
    
    # Install Rust
    COPY rust-toolchain /rust-toolchain
    RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain $(cat /rust-toolchain) && \
        . $HOME/.cargo/env
    
    # Copy and build the Rust project
    COPY . /nexeo-sts
    
    RUN . $HOME/.cargo/env && \
        cargo install --path /nexeo-sts --root /
    
    # ---- Runtime Stage ----
    FROM ubuntu:24.04
    
    LABEL maintainer="Nikola Whallon <nikola@deepgram.com>"
    
    ENV DEBIAN_FRONTEND=noninteractive
    
    RUN apt-get clean && apt-get update && \
        apt-get install -y --no-install-recommends \
            ca-certificates \
            libpq5 \
            libssl3 \
            libwebrtc-audio-processing1 && \
        apt-get clean
    
    # Copy LibTorch from the build stage
    COPY --from=builder /opt/libtorch /opt/libtorch
    ENV LIBTORCH=/opt/libtorch
    ENV LD_LIBRARY_PATH=/opt/libtorch/lib:$LD_LIBRARY_PATH
    
    # Copy the compiled binary from the build stage
    COPY --from=builder /bin/nexeo-sts /bin/nexeo-sts
    
    ENTRYPOINT ["/bin/nexeo-sts"]