import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

import 'browser/browser_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();
  runApp(const InternetBrowserApp());
}

class InternetBrowserApp extends StatelessWidget {
  const InternetBrowserApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Internet Browser',
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.system,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF346B91)),
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF78B6DF),
          brightness: Brightness.dark,
        ),
      ),
      home: const BrowserScreen(),
    );
  }
}
