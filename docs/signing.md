# Code signing (Windows) with SignPath

Windows release builds can be signed through [SignPath Foundation](https://signpath.org), which
signs open-source projects for free. Until the steps below are done, releases are built
unsigned and everything else works the same.

## 1. Apply (once)

Apply at <https://signpath.org/apply> with:

- **Project:** Quire, <https://github.com/Quezka/quire>, licence GPL-3.0-or-later
- **Description:** desktop app for notes, a day planner, a school timetable and the Classeviva
  school register; Windows installer built with PyInstaller + Inno Setup on GitHub Actions
- **Downloads:** GitHub releases (`Quire-<version>-windows-x64-setup.exe`)
- **Maintainer:** Quezka (arsdom15@gmail.com)

The README already has the "Code signing policy" and "Privacy" sections SignPath asks for.

## 2. Set up the SignPath project (after approval)

In the SignPath web app:

1. **Trusted build systems:** add *GitHub.com* and link it to the project.
2. **Project** with slug `quire`, repository `https://github.com/Quezka/quire`.
3. **Artifact configurations**
   - slug `app`: signs only Quire's own executable inside the app folder:
     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="Quire.exe">
           <authenticode-sign/>
         </pe-file>
       </zip-file>
     </artifact-configuration>
     ```
   - slug `installer`: signs the setup:
     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="*-setup.exe">
           <authenticode-sign/>
         </pe-file>
       </zip-file>
     </artifact-configuration>
     ```
4. **Signing policy** with slug `release-signing`, using the SignPath Foundation release
   certificate, with manual approval by the maintainer. Restrict its origin to tags `v*` built
   by `.github/workflows/build.yml`.
5. Create an **API token** for a CI user that may submit requests to that policy.

## 3. Connect GitHub

In the repository's *Settings → Secrets and variables → Actions*:

- secret `SIGNPATH_API_TOKEN`: the API token
- variable `SIGNPATH_ORGANIZATION_ID`: your SignPath organisation id

From then on, every tag `vX.Y.Z` builds, sends `Quire.exe` and then the installer to SignPath,
waits for your approval, and publishes the signed setup.
