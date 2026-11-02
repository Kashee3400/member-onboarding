# Mobile

`member_onboarding` is a Flutter package holding the facilitator's form. Any Flutter
app can open it as a screen. The app keeps its own login: the package only needs a way
to get a signed assertion for the current user.

This folder pins Flutter with FVM. Run commands with `fvm flutter`.

## Add it to a host app

1. Depend on the package:

   ```yaml
   dependencies:
     member_onboarding:
       path: ../member_onboarding
   ```

2. Open the screen:

   ```dart
   Navigator.of(context).push(
     MaterialPageRoute(
       builder: (_) => MemberOnboardingScreen(
         config: MemberOnboardingConfig(
           baseUrl: 'https://onboarding.example.com',
           assertionProvider: () => hostApi.fetchOnboardingAssertion(),
         ),
       ),
     ),
   );
   ```

   `assertionProvider` calls the host's own backend. For `erp_master` that is
   `POST /management/api/auth/member-onboarding/token/`, which returns `assertion`.

3. Allow the device features.

   Android, in `AndroidManifest.xml`:

   ```xml
   <uses-permission android:name="android.permission.INTERNET" />
   <uses-permission android:name="android.permission.CAMERA" />
   <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
   <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
   ```

   iOS, in `Info.plist`: `NSCameraUsageDescription` and
   `NSLocationWhenInUseUsageDescription`.

If an Android build fails with "Could not close incremental caches" on Windows, add
`kotlin.incremental=false` to the host's `android/gradle.properties`. The example app does.

## How it behaves

- Every change is saved on the phone at once, in the keystore-encrypted store, then
  synced in the background. After one online start, forms can be filled with no network.
  Finished forms still need the network for final submission.
- Aadhaar and account numbers leave the phone as soon as the server has them, and
  uploaded pictures are deleted from it.
- The form comes from the server, so most changes need no app release.
- Forms belong to the MPP. If an MPP moves while a draft sits unsynced on a phone, the
  server refuses that draft and it stays on the phone, so sync before handing over.

## Tests

```
cd member_onboarding
fvm flutter test
fvm flutter analyze
```
