FROM golang:1.26-alpine
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o ege-server main.go
EXPOSE 8080
CMD ["./ege-server"]