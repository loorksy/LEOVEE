FROM ghcr.io/cirruslabs/flutter:stable AS build
WORKDIR /app
COPY pubspec.yaml ./
RUN flutter pub get
COPY . .
RUN flutter pub get && flutter build apk --release

FROM alpine:3.20
WORKDIR /out
COPY --from=build /app/build/app/outputs/flutter-apk/app-release.apk /out/app-release.apk
CMD ["cp", "/out/app-release.apk", "/apk/app-release.apk"]
