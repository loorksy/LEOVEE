import 'package:flutter/material.dart';

class EnvField extends StatelessWidget {
  const EnvField({
    super.key,
    required this.controller,
    required this.label,
    required this.hint,
    this.obscure = true,
    this.keyboardType,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final bool obscure;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboardType,
      decoration: InputDecoration(
        labelText: label,
        helperText: hint,
        helperMaxLines: 2,
        alignLabelWithHint: true,
      ),
    );
  }
}
