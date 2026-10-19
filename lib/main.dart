import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:media_kit/media_kit.dart';

import 'browser/browser_screen.dart';
import 'browser/welcome_preferences.dart';
import 'browser/welcome_screen.dart';

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
      home: const FirstRunGate(),
    );
  }
}


/// A fresh Android install sees AdBlock once, without touching legacy data.
class FirstRunGate extends StatefulWidget {
  const FirstRunGate({super.key});

  @override
  State<FirstRunGate> createState() => _FirstRunGateState();
}

class _FirstRunGateState extends State<FirstRunGate> {
  late final Future<bool> _needsWelcome;
  bool _continued = false;

  @override
  void initState() {
    super.initState();
    _needsWelcome = _resolveWelcome();
  }

  Future<bool> _resolveWelcome() async {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return false;
    }
    final preferences = await SharedPreferences.getInstance();
    return WelcomePreferences.shouldShow(preferences, onAndroid: true);
  }

  Future<void> _finishWelcome() async {
    final preferences = await SharedPreferences.getInstance();
    await WelcomePreferences.markCompleted(preferences);
    if (mounted) {
      setState(() => _continued = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_continued) {
      return const BrowserScreen();
    }
    return FutureBuilder<bool>(
      future: _needsWelcome,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Scaffold(
            body: Center(
              child: SelectableText(
                '첫 실행 설정을 불러오지 못했습니다: ${snapshot.error}',
              ),
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (snapshot.data!) {
          return WelcomeScreen(onContinue: _finishWelcome);
        }
        return const BrowserScreen();
      },
    );
  }
}
