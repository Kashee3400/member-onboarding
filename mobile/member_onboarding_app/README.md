# Member Forms (standalone app)

For organizations with no app of their own. Field staff sign in with the mobile
number their office registered and a code by SMS, then fill member forms exactly
as in an app that embeds the `member_onboarding` package.

## Before it works for an organization

1. The organization's SMS gateway is set up under **Integrations**: the sign-in
   code goes out through it.
2. Each facilitator is added under **Staff** with their mobile number (an email is
   optional), given the Facilitator role, and given MPPs under **Assignments**.
3. Roles that need MFA (Organization Admin, CS & Legal, Finance) cannot sign in
   here: they use the staff portal.

## Running

```bash
fvm flutter run --dart-define=MEMBER_ONBOARDING_URL=https://support.kasheemilk.com
```

The URL defaults to `https://support.kasheemilk.com`. Push notifications are not
set up in this app yet: it needs its own Firebase project first.
