# Adding Member Forms to your own app

This guide is for the developers of an organization's app. It explains how to
put the member onboarding forms inside an existing Flutter app, so field staff
fill member forms without a second app or a second login.

If your organization has no app, or its app is not built with Flutter, use the
standalone **Member Forms** app instead (`mobile/member_onboarding_app`). Staff
there sign in with their mobile number and a code by SMS, and nothing below is
needed.

## How it fits together

```
 Your app ──(1) "who is this?"──▶ Your backend
    │                                 │ signs a short-lived token (RS256)
    │◀────────(2) assertion ──────────┘
    │
    └──(3) assertion ──▶ Member onboarding service ──▶ access token
                         (checks the signature with your public key)
```

1. When the forms need access, the package asks your app for an **assertion**.
2. Your app asks your own backend, which knows who is signed in, to sign one.
3. The package swaps it at the onboarding service for an access token.

Your users never sign in twice, and when someone leaves your app (signed out or
disabled), their access to the forms ends with it. The MPPs listed in the
assertion become the MPPs they work, so moving an MPP in your system moves it
here on their next use.

## 1. Add the package

The package lives in the `member-onboarding` repository. Ask the platform
operator for read access, then in your app's `pubspec.yaml`:

```yaml
dependencies:
  member_onboarding:
    git:
      url: git@github.com:Kashee3400/member-onboarding.git
      path: mobile/member_onboarding
      ref: main        # or a tag the operator gives you
```

It needs Flutter 3.32 or later and Android 6 (minSdk 23) or later. Add these
Android permissions, used for document photos, the Aadhaar QR and the visit's
location:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

On iOS, add `NSCameraUsageDescription`, `NSLocationWhenInUseUsageDescription`
and `NSPhotoLibraryUsageDescription` to `Info.plist`.

## 2. Open the screen

One widget is the whole feature. Open it full screen from a menu item:

```dart
import 'package:member_onboarding/member_onboarding.dart';

MemberOnboardingScreen(
  config: MemberOnboardingConfig(
    baseUrl: 'https://support.kasheemilk.com',
    assertionProvider: () async {
      // Your backend, called with your app's own session.
      final response = await myApi.post('/member-onboarding/token/');
      return response.data['assertion'] as String;
    },
    primaryColor: const Color(0xFF0F6CBD),        // optional
    pushTokenProvider: () => FirebaseMessaging.instance.getToken(), // optional
  ),
)
```

The package handles everything else: drafts saved offline, photos kept
encrypted on the phone until the form is sent, retries, and the list of the
facilitator's own forms.

## 3. Sign assertions on your backend

Make an RSA key pair of at least 2048 bits, once:

```bash
openssl genrsa -out member_onboarding_private.pem 2048
openssl rsa -in member_onboarding_private.pem -pubout -out member_onboarding_public.pem
```

Keep the private key secret on your backend, for example in an environment
variable. Never put it in the app. The public key goes into the portal in step 4.

Add an endpoint that only a signed-in field user can call and that returns
`{"assertion": "<token>"}`. The token is a JWT signed with **RS256**:

| Claim | Value |
|---|---|
| `iss` | Your app's issuer name, exactly as registered in step 4, e.g. `acme-app` |
| `aud` | `member-onboarding`, unless the operator tells you otherwise |
| `sub` | Your user's permanent id. Never reuse one for another person |
| `name` | The person's name, shown on forms and in history |
| `mpps` | List of the ERP codes of the MPPs they work, e.g. `["090012345"]` |
| `iat` | Now, in seconds |
| `exp` | At most 300 seconds after `iat`. 120 is a good choice |
| `jti` | A new random id for every token. Each token works once |

Python (PyJWT):

```python
import time, uuid, jwt

def member_onboarding_assertion(user, mpp_codes, private_key):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "acme-app",
            "aud": "member-onboarding",
            "sub": str(user.id),
            "name": user.get_full_name(),
            "mpps": sorted(mpp_codes),
            "iat": now,
            "exp": now + 120,
            "jti": uuid.uuid4().hex,
        },
        private_key,
        algorithm="RS256",
    )
```

Node.js (jsonwebtoken):

```js
const jwt = require("jsonwebtoken");
const { randomUUID } = require("crypto");

function memberOnboardingAssertion(user, mppCodes, privateKey) {
  return jwt.sign(
    { sub: String(user.id), name: user.fullName, mpps: [...mppCodes].sort(), jti: randomUUID() },
    privateKey,
    { algorithm: "RS256", issuer: "acme-app", audience: "member-onboarding", expiresIn: 120 },
  );
}
```

Java (jjwt 0.12):

```java
String assertion = Jwts.builder()
    .issuer("acme-app")
    .audience().add("member-onboarding").and()
    .subject(user.getId().toString())
    .claim("name", user.getFullName())
    .claim("mpps", mppCodes)
    .issuedAt(new Date())
    .expiration(new Date(System.currentTimeMillis() + 120_000))
    .id(UUID.randomUUID().toString())
    .signWith(privateKey, Jwts.SIG.RS256)
    .compact();
```

The MPP codes must be the same codes the organization's masters were imported
with (the `mpp_internal_code` column of the masters Excel). A code the service
does not know is ignored, so someone whose codes are all unknown signs in but
sees no MPPs. Refuse to sign an assertion for a user with no MPPs at all.

If one backend serves several organizations (one ERP for several companies),
each organization registers the same issuer and key in its own Connected Apps.
A person then goes to the organization that owns their MPPs; MPPs in two
organizations at once are refused.

## 4. Register your app

The organization's admin opens **Administration → Connected Apps → Connect an
app** in the staff portal and enters:

- **Issuer:** exactly your `iss`.
- **Audience:** exactly your `aud`.
- **Public key:** the contents of `member_onboarding_public.pem`.
- **Role on first sign-in:** usually *Facilitator*. Roles that need MFA cannot
  be given this way.
- **Take MPP assignments from this app:** on, so your MPP list is the truth.

## 5. Notifications (optional)

When a form is sent back to a facilitator, the service can push a notification
to their phone through Firebase Cloud Messaging:

1. Pass `pushTokenProvider` (step 2). The package registers the phone's token.
2. The organization's admin pastes your Firebase project's service account key
   under **Integrations → Push** and presses *Check the key with Google*.
3. The message carries this data, so your app can open the right form:

   ```json
   {"source": "member_onboarding", "type": "application_rejected", "application_id": "<id>"}
   ```

   Open `MemberOnboardingScreen(openApplicationId: <id>, ...)` when it is tapped.

## Apps that sign in to the service themselves

If your app does not have its own users but signs people in to this service
directly (as the standalone app does), give `accessTokenProvider` instead of
`assertionProvider`. It must return a valid access token for this service, and
a fresh one when called with `renew: true`.

## Checking it works

- [ ] Your token endpoint refuses a caller who is not signed in.
- [ ] A token decodes at jwt.io with the claims above, and `exp - iat` ≤ 300.
- [ ] Opening the forms shows the person's MPPs on the home screen.
- [ ] The same token sent twice is refused the second time.
- [ ] Moving an MPP to someone else in your system moves it in the forms on
      their next use.
- [ ] Signing out of your app ends access to the forms.

## When the forms say "could not sign in"

Every refusal looks the same to the app, on purpose. The platform operator can
see the reason in the service log. The usual ones:

| Reason in the log | Fix |
|---|---|
| `unknown_issuer` | `iss` differs from the Connected Apps entry, or the entry is off |
| `InvalidSignatureError` | The public key in the portal does not match your private key |
| `InvalidAudienceError` | `aud` differs from the Connected Apps entry |
| `lifetime_too_long` | `exp` is more than 300 seconds after `iat` |
| `replayed` | A token was sent twice: make a new `jti` each time |
| `ExpiredSignatureError` | The server clock is off, or the token was cached |
| `no_organization_owns_the_mpps` | The MPP codes are not in the organization's masters |
