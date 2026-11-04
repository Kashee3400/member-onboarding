/// App wording, in English like the rest of the host app. Field labels come from the
/// server with the form.
/// What the OTP steps say when they cannot go ahead.
class OtpWords {
  const OtpWords._();

  static const offline = 'No network. Send the OTP once the network is back.';
  static const notSaved = 'The form is not saved yet. Try again in a moment.';
}

/// Said on the field itself when what was typed already belongs to someone else.
class Taken {
  const Taken._();

  static const aadhaar =
      'This Aadhaar number is already on another form or member. Enter the right number.';
  static const mobile =
      "This mobile number is already on another form or member. Enter the member's own number.";
  static const email = "This email is already on another form. Enter the member's own email.";
  static const account =
      "This bank account is already on another form. Enter the member's own account.";

  static String? forPath(String path) => switch (path) {
    'address.mobile' => mobile,
    'address.email' => email,
    'bank.account_number' => account,
    _ => null,
  };
}

class Strings {
  const Strings._();

  static const title = 'Member Forms';
  static const newForm = 'New form';
  static const chooseMpp = 'Choose MPP';
  static const searchMpp = 'Search for MPP...';
  static const myDrafts = 'Unfinished forms';
  static const sentBack = 'Sent back for correction';
  static const startTitle = 'Start a new member form';
  static const startHint = 'Fill it in the village. It saves on the phone even without network.';
  static const mppsAssigned = 'MPPs assigned';
  static const noDrafts = 'No unfinished forms';
  static const noDraftsHint = 'Forms you start stay here until you submit them.';
  static const waitingUpload = 'Waiting to upload';
  static const correct = 'Correct';
  static const untitled = 'No name yet';
  static const loadFailed = 'Could not load. Check the internet and try again.';
  static const retry = 'Try again';
  static const offlineReady = 'No network. You can fill forms; they are sent when the network is back.';
  static const firstRunNeedsNetwork = 'The internet is needed the first time.';

  static const myRecords = 'My records';
  static const today = 'Today';
  static const yesterday = 'Yesterday';
  static const thisWeek = 'This week';
  static const thisMonth = 'This month';
  static const pickDates = 'Pick dates';
  static const started = 'Started';
  static const sent = 'Submitted';
  static const waiting = 'Under review';
  static const approved = 'Became members';
  static const returned = 'Sent back';
  static const all = 'All';
  static const drafts = 'Unfinished';
  static const showMore = 'Show more';
  static const noRecords = 'No forms in these dates';
  static const startedOn = 'Started';
  static const sentOn = 'Submitted';
  static const recordsNeedNetwork = 'The internet is needed to see records.';
  static const mpp = 'MPP';
  static const formNumber = 'Form number';
  static const mobileLabel = 'Mobile';
  static const approvals = 'Approvals';
  static const stageApproved = 'Approved';
  static const stageReturned = 'Sent back';
  static const stagePending = 'Waiting';
  static const stageNotYet = 'Not reached yet';
  static const days = 'days';
  static const editForm = 'Edit form';
  static const correctForm = 'Correct the form';
  static const draftStatus = 'Draft';
  static const memberFee = 'Member fee';
  static const admissionFee = 'Admission fee';
  static const shares = 'Shares';
  static const totalToPay = 'Total to pay';
  static const feeHint = 'Tell the member this amount before she signs.';
  static const sharesFromMilk = 'taken from her milk payments, not paid now.';
  static const sentBackAlertTitle = 'Forms sent back for correction';
  static const sentBackAlertBody = 'These forms were sent back. Open one to correct it and submit again.';
  static const later = 'Later';
  static const savedOn = 'Saved';

  static const back = 'Back';
  static const next = 'Next';
  static const step = 'Step';
  static const required = 'This is required';
  static const optional = 'Optional';
  static const choose = 'Choose';
  static const fromMpp = 'From the MPP';

  static const saved = 'Saved';
  static const saving = 'Saving';
  static const offline = 'Saved on the phone, sent when the network is back';
  static const conflict = 'This form was changed somewhere else';
  static const useServerCopy = 'Get the latest';
  static const syncFailed = 'Could not send';

  static const aadhaarNumber = 'Aadhaar number';
  static const aadhaarInvalid = 'Enter a valid 12-digit Aadhaar number';
  static const scanAadhaar = 'Scan Aadhaar QR';
  static const scanFirst =
      'Start here: the QR fills in her name, birth date, relation and address for the next steps.';
  static const scanHint = 'Keep the QR code inside the box';
  static const scanFailed =
      'Could not read the QR. If the card is old or worn, scan the QR in the member\'s '
      'mAadhaar app or on her e-Aadhaar instead, or fill it in by hand';
  static const filledFromPhoto =
      'The Aadhaar QR in the photo filled in her details. Check them on the next steps';
  static const scanConsentTitle = 'Ask the member first';
  static const scanConsent =
      'Her Aadhaar QR will be read to fill in and verify her details with UIDAI\'s '
      'signature. Does she agree?';
  static const scanConsentYes = 'She agrees';
  static const scanConsentNo = 'Not now';
  static const aadhaarVerified = 'Verified with UIDAI\'s signature';
  static const aadhaarUnsigned = 'Older QR, not signed: the office checks by eye';
  static const aadhaarNotUidai = 'This QR is not signed by UIDAI. Check the card';
  static const aadhaarWaiting = 'Scanned. Verified when the form is next saved';
  static const scanCheck = 'Check the details the scan filled in';

  static const useLocation = 'Use current location';
  static const locationFailed = 'Could not get the location. Turn on GPS and try again.';
  static const locationSaved = 'Location taken';

  static const accountNumber = 'Bank account number';
  static const accountAgain = 'Account number again';
  static const accountMismatch = 'The two account numbers do not match';

  static const family = 'Household members';
  static const addPerson = 'Add person';
  static const removePerson = 'Remove';
  static const name = 'Name';
  static const gender = 'Gender';
  static const age = 'Age';
  static const relation = 'Relation';

  static const documents = 'Documents';
  static const photo = "Member's photo";
  static const aadhaarFront = 'Aadhaar front';
  static const aadhaarBack = 'Aadhaar back';
  static const passbook = 'Bank passbook';
  static const takePhoto = 'Take photo';
  static const signOut = 'Sign out';
  static const signingDeclares = 'By signing, the member declares:';
  static const useCamera = 'Take a photo with the camera';
  static const fromGallery = 'Choose from the gallery';
  static const retake = 'Retake';
  static const memberSignature = "Member's signature";
  static const signHere = 'Sign here';
  static const clear = 'Clear';
  static const saveSignature = 'Keep signature';
  static const signatureSaved = 'Signature taken';
  static const cannotWrite = 'Cannot sign? Take a thumbprint';
  static const thumbprint = 'Thumbprint';

  static const photoDark = 'The photo is too dark';
  static const photoBlurry = 'The photo looks blurred';
  static const photoHelp =
      'Retake it in good light, holding the phone still, with the whole card in the frame. '
      'A blurred photo can get the form sent back.';
  static const keepAnyway = 'Keep anyway';
  static const photoDoubt = 'Check it: the photo did not look clear';

  static const verifyMobile = 'Verify mobile number';
  static const verifyEmail = 'Verify email';
  static const verified = 'Verified';
  static const notVerified = 'Not verified';
  static const sendOtp = 'Send OTP';
  static const resendOtp = 'Resend OTP';
  static const resendIn = 'Resend in';
  static const otpSent = "OTP sent to the member's phone. Ask them for it and enter it below.";
  static const otpSentEmail = "OTP sent to the member's email. Ask them for it and enter it below.";
  static const otpCode = '6-digit OTP';
  static const checkOtp = 'Verify';
  static const enterMobileFirst = 'Enter the mobile number first';
  static const enterEmailFirst = 'Enter the email first';
  static const mobileNotVerified = 'Mobile number not verified';
  static const emailNotVerified = 'Email not verified';

  static const review = 'Review';
  static const checklist = 'Steps';
  static const stepDone = 'Done';
  static const stepLeft = 'Left';
  static const toCorrect = 'Sent back to correct these';
  static const corrected = 'Changed';
  static const notCorrected = 'Not changed yet';
  static const stillNeeded = 'Still needed';
  static const allFilled = 'Everything is filled in. You can submit.';
  static const submit = 'Submit form';
  static const submitted = 'Form submitted';
  static const done = 'OK';
  static const rejectedBecause = 'Why it was sent back';
  static const fixFirst = 'Not submitted. Please fix these:';
  static const pleaseCheck = 'Fix these, or the form will not submit';

  // Checked while typing, by the same rules the server applies on submit.
  static const aadhaarChecksum = 'This Aadhaar number is not valid. Check each digit against the card';
  static const accountInvalid = 'An account number has 9 to 18 digits';
  static const mobileInvalid = 'A mobile number has 10 digits and starts with 6, 7, 8 or 9';
  static const pincodeInvalid = 'A PIN code has 6 digits and does not start with 0';
  static const emailInvalid = 'This email is not valid, e.g. name@gmail.com';
  static const ifscInvalid = 'An IFSC has 11 characters, e.g. SBIN0001234 (the 5th is a zero)';
  static const dateInvalid = 'This date is not valid';
  static const applicantTooYoung = 'The member must be at least 18 years old';
  static const applicantTooOld = 'The age comes to over 100. Check the date of birth';
  static const notANumber = 'Numbers only, e.g. 5 or 5.5';
  static const productionNeeded = 'Enter a daily milk production above 0';
  static const consumptionTooHigh = 'Household use cannot be more than the milk produced';
  static const noAnimals = 'Enter the count of at least one animal';
  static const guardianNeeded = "The nominee is under 18. Enter a guardian's name";
  static const guardianNotNeeded = 'The nominee is an adult. Leave the guardian empty';
  static const familyAgeInvalid = 'Enter an age from 0 to 120';

  // The step screens.
  static const documentsIntro = 'Take each photo clearly. Tap a photo to see it full size.';
  static const photoHint = 'Face clearly visible, plain background';
  static const cardHint = 'Whole card inside the frame';
  static const passbookHint = 'The page with the account number';
  static const checkPhoto = 'Check photo';
  static const uploaded = 'Uploaded';
  static const onPhone = 'On phone';
  static const tapToZoom = 'Tap to see it full size';
  static const years = 'years';
  static const fromQr = 'From Aadhaar QR';
  static const memberDetails = 'Member details';
  static const fromMppTitle = 'From the MPP';
  static const addressTitle = 'Address';
  static const contactTitle = 'Contact';
  static const locationTitle = 'Location of the form';
  static const locationAgain = 'Take the location again';
  static const animalsTitle = 'Animals';
  static const milkTitle = 'Milk';
  static const milkToSell = 'Surplus Milk';
  static const litresPerDay = 'litres a day';
  static const findingBranch = 'Finding the bank and branch';
  static const branchNotFound = 'Bank not found for this IFSC. Type the bank and branch.';
  static const accountsMatch = 'Both account numbers match';
  static const bankTitle = 'Bank';
  static const sameAsMember = "Use member's name";
  static const cancel = 'Cancel';
  static const familyIntro = 'Everyone who lives with the member.';
  static const noFamily = 'No household members added yet';
  static const editPerson = 'Edit person';
  static const savePerson = 'Save';
  static const chooseFromFamily = 'Choose from the household';
  static const nomineeTitle = 'Nominee';
  static const yearOnlyHint = 'Only the age known? The date is set to 1 January of that year.';
  static const sameAddress = "Same as the member's address";
  static const signLast = 'The member signs last, after the whole form has been read to them.';
  static const signAgain = 'Sign again';
  static const thumbprintAgain = 'Take the thumbprint again';
  static const submittedHint = 'It now goes to the Area Manager for checking.';
  static const finishStepFirst = 'Complete this step before going on.';
  static const completeToContinue = 'Complete these to continue';

  // The animal count grid, laid out like the printed form.
  static const heifer = 'Heifer';
  static const dry = 'Dry';
  static const inMilk = 'In milk';
  static const indigenous = 'Indigenous';
  static const crossbred = 'Crossbred';
  static const buffalo = 'Buffalo';
  static const total = 'Total';
}
