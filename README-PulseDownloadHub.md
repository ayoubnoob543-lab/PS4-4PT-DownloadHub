# 4PT Download Hub — generic file branch

Variante de trabajo basada en PS4-4PT para aceptar descargas directas de archivos genéricos además de PKG.

## Formatos

La entrada de URL directa conserva la extensión del enlace y permite `.zip`, `.7z`, `.json`, `.bin`, `.txt` y otros archivos HTTP; los `.pkg` mantienen el flujo normal de instalación. Los archivos genéricos se guardan y pueden pausarse/reanudarse, pero no se instalan como PKG.

## Estado de compilación

Este repositorio contiene el código fuente modificado. Para obtener `PAPT00275.pkg` hace falta el OpenOrbis PS4 Toolchain (`OO_PS4_TOOLCHAIN`) y `yaml-cpp`. El sandbox actual no incluye ese toolchain, por lo que aquí no se publica un PKG inventado ni instalable.

## Uso en la PS4

El navegador de la PS4 no puede usar este repositorio para ejecutar la app. La URL del repositorio solo sirve para descargar el código desde un PC. Cuando exista un PKG compilado, se instala con GoldHEN Package Installer/4PT y luego se abre desde el menú de aplicaciones.

No hay una URL de navegador que convierta automáticamente este código en una app nativa.
