class ChoiceOption {
  const ChoiceOption({required this.value, required this.label});

  factory ChoiceOption.fromJson(Map<String, dynamic> json) => ChoiceOption(
    value: json['value'] as String,
    label: (json['label_hi'] ?? json['label']) as String,
  );

  final String value;
  final String label;
}

List<ChoiceOption> _choices(Object? json) => ((json as List?) ?? const [])
    .cast<Map<String, dynamic>>()
    .map(ChoiceOption.fromJson)
    .toList();

/// The label to show for a saved value. Retired choices still read; a value no list
/// knows, such as a nominee relation typed before it was a list, shows as typed.
String? choiceLabel(String? value, List<ChoiceOption> options, List<ChoiceOption> retired) {
  if (value == null || value.isEmpty) return null;
  for (final option in [...options, ...retired]) {
    if (option.value == value) return option.label;
  }
  return value;
}

class FormFieldSpec {
  const FormFieldSpec({
    required this.key,
    required this.label,
    required this.type,
    required this.required,
    this.options = const [],
    this.retired = const [],
  });

  factory FormFieldSpec.fromJson(Map<String, dynamic> json) => FormFieldSpec(
    key: json['key'] as String,
    label: (json['label_hi'] ?? json['label']) as String,
    type: json['type'] as String,
    required: json['required'] as bool,
    options: _choices(json['options']),
    retired: _choices(json['retired_options']),
  );

  final String key;
  final String label;
  final String type;
  final bool required;

  /// What can be chosen today.
  final List<ChoiceOption> options;

  /// No longer offered, but shown when an older form holds one.
  final List<ChoiceOption> retired;
}

class FormSectionSpec {
  const FormSectionSpec({required this.key, required this.title, required this.fields});

  factory FormSectionSpec.fromJson(Map<String, dynamic> json) => FormSectionSpec(
    key: json['key'] as String,
    title: (json['title_hi'] ?? json['title']) as String,
    fields: (json['fields'] as List)
        .cast<Map<String, dynamic>>()
        .map(FormFieldSpec.fromJson)
        .toList(),
  );

  final String key;
  final String title;
  final List<FormFieldSpec> fields;
}

/// The form as the server defines it, so the app shows exactly what is validated.
/// The organization's lists come inside it, so the cached copy works offline too.
class FormSchema {
  const FormSchema({
    required this.version,
    required this.sections,
    required this.maxFamilyMembers,
    required this.familyGenders,
    required this.familyRelations,
    this.retiredGenders = const [],
    this.retiredRelations = const [],
  });

  factory FormSchema.fromJson(Map<String, dynamic> json) {
    final family = json['family'] as Map<String, dynamic>;

    return FormSchema(
      version: json['version'] as int,
      sections: (json['sections'] as List)
          .cast<Map<String, dynamic>>()
          .map(FormSectionSpec.fromJson)
          .toList(),
      maxFamilyMembers: family['max_members'] as int,
      familyGenders: _choices(family['genders']),
      familyRelations: _choices(family['relations']),
      retiredGenders: _choices(family['retired_genders']),
      retiredRelations: _choices(family['retired_relations']),
    );
  }

  final int version;
  final List<FormSectionSpec> sections;
  final int maxFamilyMembers;
  final List<ChoiceOption> familyGenders;
  final List<ChoiceOption> familyRelations;
  final List<ChoiceOption> retiredGenders;
  final List<ChoiceOption> retiredRelations;

  FormSectionSpec section(String key) => sections.firstWhere((item) => item.key == key);
}
