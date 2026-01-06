FROM golang:1.23-alpine AS builder

WORKDIR /app

COPY go.mod .
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o hub-node ./cmd/hub-node

FROM debian:bookworm-slim

WORKDIR /app

COPY --from=builder /app/hub-node .

EXPOSE 8080

CMD ["./hub-node"]
