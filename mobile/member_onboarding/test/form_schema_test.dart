import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/models/form_schema.dart';

Map<String, dynamic> option(String value, String label, String hindi) => {
  'value': value,
  'label': label,
  'label_hi': hindi,
};

final json = <String, dynamic>{
  'version': 1,
  'family': {
    'max_members': 6,
    'genders': [option('male', 'Male', 'पुरुष')],
    'relations': [option('husband', 'Husband', 'पति')],
    'retired_relations': [option('brother', 'Brother', 'भाई')],
  },
  'sections': [
    {
      'key': 'nominee',
      'title': 'Nominee',
      'title_hi': 'नामित',
      'fields': [
        {
          'key': 'relation',
          'label': 'Relation with applicant',
          'label_hi': 'आवेदक के साथ संबंध',
          'type': 'choice',
          'required': true,
          'option_list': 'nominee_relation',
          'options': [option('son', 'Son', 'पुत्र')],
          'retired_options': [option('other', 'Other', 'अन्य')],
        },
      ],
    },
  ],
};

void main() {
  test('choices read in English, retired ones kept apart', () {
    final schema = FormSchema.fromJson(json);
    final relation = schema.section('nominee').fields.single;

    expect(relation.type, 'choice');
    expect(relation.options.single.label, 'Son');
    expect(relation.retired.single.value, 'other');
    expect(schema.retiredRelations.single.label, 'Brother');
    expect(schema.retiredGenders, isEmpty);
  });

  test('a schema from before retired choices still reads', () {
    final older = {
      ...json,
      'family': {
        'max_members': 6,
        'genders': [option('male', 'Male', 'पुरुष')],
        'relations': [option('husband', 'Husband', 'पति')],
      },
    };

    expect(FormSchema.fromJson(older).retiredRelations, isEmpty);
  });

  test('a saved value is named from either list, or shown as typed', () {
    final relation = FormSchema.fromJson(json).section('nominee').fields.single;
    String? label(String? value) => choiceLabel(value, relation.options, relation.retired);

    expect(label('son'), 'Son');
    expect(label('other'), 'Other');
    expect(label('Grandson'), 'Grandson');
    expect(label(''), isNull);
    expect(label(null), isNull);
  });
}
