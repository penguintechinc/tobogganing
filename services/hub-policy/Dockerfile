FROM golang:1.24-bookworm@sha256:PLACEHOLDER AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/hub-policy ./cmd/

FROM debian:bookworm-slim@sha256:PLACEHOLDER
COPY --from=builder /app/hub-policy /hub-policy
CMD ["/hub-policy"]
