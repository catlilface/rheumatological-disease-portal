FROM golang:1.27-alpine AS build
WORKDIR /src
COPY services/bff/go.mod services/bff/go.sum ./
RUN go mod download
COPY services/bff/internal ./internal
COPY services/bff/cmd ./cmd
RUN CGO_ENABLED=0 go build -trimpath -o /out/bff ./cmd/bff

FROM alpine:3.23
# nc is used only by the Compose/Kubernetes network-isolation smoke check.
RUN apk add --no-cache netcat-openbsd
WORKDIR /app
COPY contracts/http /app/contracts/http
COPY --from=build /out/bff /usr/local/bin/bff
USER 10001:10001
EXPOSE 8000
CMD ["bff"]
