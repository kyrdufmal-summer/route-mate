#!/usr/bin/env bash
# ROUTE MATE 차량용 앱 release APK 빌드 (Gradle 없이 Android SDK 빌드 도구로 직접 빌드)
# 필요: JDK 17 (JAVA_HOME), Android SDK build-tools 34.0.0 + platform android-30 이상 (ANDROID_SDK)
# 서명 키는 저장소 밖(KEYSTORE)에 둔다.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_SDK:?ANDROID_SDK 를 설정하세요}"
BT="$SDK/build-tools/34.0.0"
JAR="$(ls -d "$SDK"/platforms/*/android.jar | tail -1)"
KEYSTORE="${KEYSTORE:?KEYSTORE(서명 키 경로)를 설정하세요}"
KS_PASS="${KS_PASS:?KS_PASS 를 설정하세요}"
OUT="${OUT:-../apk/ROUTEMATE_release.apk}"

rm -rf build && mkdir -p build/gen build/classes build/dex
"$BT/aapt2" compile --dir res -o build/res.zip
"$BT/aapt2" link -o build/base.apk -I "$JAR" --manifest AndroidManifest.xml --java build/gen \
  --min-sdk-version 28 --target-sdk-version 34 --version-code 1 --version-name 0.1.0 build/res.zip
javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$JAR" -d build/classes \
  $(find src build/gen -name '*.java') 2>&1 | grep -v "warning" || true
"$BT/d8.bat" --release --lib "$JAR" --min-api 28 --output build/dex $(find build/classes -name '*.class')
python -c "import zipfile,sys; z=zipfile.ZipFile('build/base.apk','a'); z.write('build/dex/classes.dex','classes.dex'); z.close()"
"$BT/zipalign" -f 4 build/base.apk build/aligned.apk
mkdir -p "$(dirname "$OUT")"
"$BT/apksigner.bat" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" --out "$OUT" build/aligned.apk
"$BT/apksigner.bat" verify --print-certs "$OUT" | head -3
echo "built: $OUT"
