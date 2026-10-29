# D1: the OTel Demo cart, built from source (EVALUATION_PLAN.md §4.1, THREAT_MODEL.md T6/T11).
#
# Reviewed copy of upstream src/cart/src/Dockerfile at tag 3.1.0 (dedc0178). Same base images,
# pinned by the same digests, and the same restore and publish commands. Two deviations:
# - no test stage: upstream runs its unit tests (an in-memory store) before publishing; they do
#   not touch the store code under test, and skipping them keeps the build short;
# - no grpc-health-probe binary: the harness checks readiness with its own gRPC call.
# The build context is assembled by build.py from the pinned checkout. NuGet restore is the only
# step with network access; nothing from this image runs on the host.
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0.401@sha256:2fa828c68761b1b8c23d7662dc134421b9d3b59fe1425fdbc80804e390cdb24d AS builder
ARG TARGETARCH

WORKDIR /usr/src/app/

COPY ./src/cart/ ./
COPY ./pb/ ./pb/

RUN dotnet restore ./src/cart.csproj -r linux-musl-$TARGETARCH
RUN dotnet publish ./src/cart.csproj -r linux-musl-$TARGETARCH --no-restore -o /cart

FROM mcr.microsoft.com/dotnet/runtime-deps:10.0.12-alpine3.23@sha256:90fa8d0a47833fdc9544fcc76b833d287d4d809625b1523a3227fa6595a4ed91

WORKDIR /usr/src/app/
COPY --from=builder /cart/ ./

ENV DOTNET_HOSTBUILDER__RELOADCONFIGONCHANGE=false

ARG CART_PORT=7070
EXPOSE ${CART_PORT}
ENTRYPOINT [ "./cart" ]
