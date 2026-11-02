class ChoiceOption {
  const ChoiceOption({required this.value, required this.label});

  factory ChoiceOption.fromJson(Map<String, dynamic> json) => ChoiceOption(
    value: json['value'] as String,
    label: (json['label_hi'] ?? json['label']) as String,
  );

  final String value;
  final String label;
}

class FormFieldSpec {
  const FormFieldSpec({
    required this.key,
    required this.label,
    required this.type,
    required this.required,
    this.options = const [],
  });

  factory FormFieldSpec.fromJson(Map<String, dynamic> json) => FormFieldSpec(
    key: json['key'] as String,
    label: (json['label_hi'] ?? json['label']) as String,
    type: json['type'] as String,
    required: json['required'] as bool,
    options: ((json['options'] as List?) ?? const [])
        .cast<Map<String, dynamic>>()
        .map(ChoiceOption.fromJson)
        .toList(),
  );

  final String key;
  final String label;
  final String type;
  final bool required;
  final List<ChoiceOption> options;
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
class FormSchema {
  const FormSchema({
    required this.version,
    required this.sections,
    required this.maxFamilyMembers,
    required this.familyGenders,
    required this.familyRelations,
  });

  factory FormSchema.fromJson(Map<String, dynamic> json) {
    final family = json['family'] as Map<String, dynamic>;
    List<ChoiceOption> options(String key) =>
        (family[key] as List).cast<Map<String, dynamic>>().map(ChoiceOption.fromJson).toList();

    return FormSchema(
      version: json['version'] as int,
      sections: (json['sections'] as List)
          .cast<Map<String, dynamic>>()
          .map(FormSectionSpec.fromJson)
          .toList(),
      maxFamilyMembers: family['max_members'] as int,
      familyGenders: options('genders'),
      familyRelations: options('relations'),
    );
  }

  final int version;
  final List<FormSectionSpec> sections;
  final int maxFamilyMembers;
  final List<ChoiceOption> familyGenders;
  final List<ChoiceOption> familyRelations;

  FormSectionSpec section(String key) => sections.firstWhere((item) => item.key == key);
}
