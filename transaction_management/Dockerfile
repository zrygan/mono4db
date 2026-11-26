# --- build stage: compile a static Go binary (frontend is embedded) ---
FROM golang:1.27 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/node .

# --- runtime stage: just the binary ---
FROM gcr.io/distroless/static-debian12
COPY --from=build /out/node /node
EXPOSE 8000
ENTRYPOINT ["/node"]
