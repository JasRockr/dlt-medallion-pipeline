# Despliegue en VMs: laboratorio (VirtualBox) y producción (GCP)

Guía operativa de "ya tengo la VM encendida, ¿qué corro?" para las 2 VMs
reales del proyecto (VM-01: extracción dlt, VM-02: orquestación Airflow +
dbt). No repite contenido ya documentado en otro lado:

- **Cómo funciona el motor de reglas / dbt / la DAG factory** → `docs/ARCHITECTURE.md`.
- **Cómo se desarrolla y prueba el pipeline en una máquina de desarrollo** → `docs/COMMANDS-PIPELINE.md`.
- **Cómo se levanta el stack de Airflow+dbt una vez Docker está instalado** → `docs/COMMANDS-PIPELINE.md` sección 11.

Esta guía cubre exactamente lo que esos documentos no cubren: los pasos de
sistema operativo (Ubuntu 24.04) para que cada VM quede lista.

## Topología (resumen)

```text
VM-01 (extracción)                          VM-02 (orquestación)
Python venv + dlt + pyodbc    --- SSH --->  Airflow (docker-compose) + dbt
conecta a MSSQL origen                      SSHOperator dispara extracción
ADC → escribe solo bronze                   ADC → lee bronze, escribe staging/curated
```

## Creación de las VMs en VirtualBox (laboratorio)

Lo que sigue asume que las VMs ya existen y tienen Ubuntu corriendo. Esto
es cómo crearlas desde cero, incluyendo la red: Bridged más Host-only en
VM-01 (necesita salir a la LAN/VPN real para alcanzar el SQL Server
origen), Host-only más NAT en VM-02 (solo necesita hablar con VM-01 y salir
a internet para actualizaciones/Docker).

Cada paso trae el comando `VBoxManage` (CLI) y, debajo, el equivalente
exacto en la interfaz gráfica de VirtualBox -- son el mismo resultado por
dos caminos distintos, se pueden mezclar sin problema (ej. crear la red
por GUI y las VMs por CLI). Si un comando de `VBoxManage` falla, la GUI es
la vía más confiable para diagnosticar qué falta (nombre exacto de una
interfaz, controlador de almacenamiento ya existente, etc.) antes de
reintentar por CLI.

### Recursos mínimos por VM

| | VM-01 (extracción) | VM-02 (orquestación) |
| --- | --- | --- |
| Mínimo viable en laptop | 2 vCPU / 4 GB RAM / 40 GB disco | 4 vCPU / 8 GB RAM / 60 GB disco |
| Paridad completa con producción (e2-standard-8) | 8 vCPU / 32 GB RAM / 100 GB disco | 8 vCPU / 32 GB RAM / 100 GB disco |

VM-02 necesita más en el escenario mínimo porque corre Docker + Postgres +
Airflow (webserver y scheduler) al mismo tiempo; dbt en sí es liviano
porque las transformaciones pesadas las ejecuta BigQuery, no la VM. Deja
al menos 2 vCPU y 4 GB de RAM libres para el host al sumar ambas VMs --
no asignes el 100% de los recursos físicos disponibles.

### 1. Red host-only (tráfico privado VM-01 ↔ VM-02)

```powershell
# Listar redes host-only existentes -- VirtualBox suele traer vboxnet0 por defecto
VBoxManage list hostonlyifs

# Si no existe ninguna, crear una
VBoxManage hostonlyif create

# Confirmar/asignar el rango -- 192.168.56.0/24 es el default de VirtualBox
VBoxManage hostonlyif ipconfig vboxnet0 --ip 192.168.56.1 --netmask 255.255.255.0
```

Las VMs recibirán IPs estáticas dentro de este rango (ej. VM-01 =
`192.168.56.10`, VM-02 = `192.168.56.11`), configuradas en Ubuntu después
de instalar el sistema (paso 6 más abajo) -- VirtualBox no activa DHCP en
una red host-only a menos que se agregue explícitamente.

**Por GUI:** VirtualBox Manager → ícono **Herramientas** (arriba, junto al
selector de VMs) → **Administrador de red** → pestaña **"Redes
solo-anfitrión"** → botón **Crear** (si la lista está vacía) → seleccionar
la red creada (`vboxnet0`) → botón **Editar** (lápiz) → pestaña
**Adaptador** → confirmar/escribir `192.168.56.1` y máscara
`255.255.255.0` → **Aplicar**.

### 2. Identificar el adaptador Bridged del host (solo VM-01)

```powershell
VBoxManage list bridgedifs | Select-String "^Name:"
```

Usa el nombre exacto que aparezca (ej. `Wi-Fi`, `Ethernet`) en el paso 3 --
es el adaptador que le da a VM-01 la misma ruta de red que tiene el host
(red privada o VPN), para que alcance el origen MSSQL igual que lo hace
hoy la máquina local.

**Por GUI:** no es un paso separado -- el nombre de la interfaz física
aparece directamente en el menú desplegable al configurar la red de VM-01
en el paso 3.

### 3. Crear VM-01 (extracción)

```powershell
VBoxManage createvm --name "VM-01-extraccion" --ostype Ubuntu_64 --register

VBoxManage modifyvm "VM-01-extraccion" `
  --cpus 4 --memory 8192 `
  --nic1 bridged --bridgeadapter1 "<nombre-del-paso-2>" `
  --nic2 hostonly --hostonlyadapter2 vboxnet0

VBoxManage createmedium disk --filename "VM-01-extraccion.vdi" --size 40960
VBoxManage storagectl "VM-01-extraccion" --name "SATA" --add sata --controller IntelAhci
VBoxManage storageattach "VM-01-extraccion" --storagectl "SATA" --port 0 --device 0 --type hdd --medium "VM-01-extraccion.vdi"
VBoxManage storageattach "VM-01-extraccion" --storagectl "SATA" --port 1 --device 0 --type dvddrive --medium "<ruta>\ubuntu-24.04-live-server-amd64.iso"
```

### 4. Crear VM-02 (orquestación) — mismo patrón, sin Bridged

```powershell
VBoxManage createvm --name "VM-02-orquestacion" --ostype Ubuntu_64 --register

VBoxManage modifyvm "VM-02-orquestacion" `
  --cpus 4 --memory 8192 `
  --nic1 hostonly --hostonlyadapter1 vboxnet0 `
  --nic2 nat

VBoxManage createmedium disk --filename "VM-02-orquestacion.vdi" --size 61440
VBoxManage storagectl "VM-02-orquestacion" --name "SATA" --add sata --controller IntelAhci
VBoxManage storageattach "VM-02-orquestacion" --storagectl "SATA" --port 0 --device 0 --type hdd --medium "VM-02-orquestacion.vdi"
VBoxManage storageattach "VM-02-orquestacion" --storagectl "SATA" --port 1 --device 0 --type dvddrive --medium "<ruta>\ubuntu-24.04-live-server-amd64.iso"
```

Ajusta `--cpus`/`--memory` a los valores de la tabla de arriba según el
host disponible (8192 MB = 8 GB; para el escenario de paridad completa,
`--memory 32768`).

**Por GUI:** VirtualBox Manager → botón **Nueva** (o Máquina → Nueva) →
asistente de creación:

1. **Nombre y sistema operativo:** nombre `VM-02-orquestacion`, tipo
   `Linux`, versión `Ubuntu (64-bit)`. Si el asistente ofrece un campo
   "ISO image", dejarlo vacío por ahora (se conecta en el paso 5).
2. **Hardware:** 4 CPUs, 8192 MB de RAM (o los valores de la tabla según
   el host).
3. **Disco duro virtual:** crear un VDI nuevo de **60 GB** (tamaño fijo o
   dinámico, ambos funcionan; fijo es más rápido en I/O una vez expandido).
4. **Finish** — la VM aparece en el panel izquierdo.
5. Seleccionar `VM-02-orquestacion` → **Configuración** → **Red**:
   - Adaptador 1: habilitar, conectado a **"Adaptador solo-anfitrión"**,
     nombre `vboxnet0`.
   - Adaptador 2: habilitar, conectado a **"NAT"** (para salida a internet
     desde VM-02: actualizaciones, `gcloud`, descarga de imágenes Docker).
6. **Aceptar**.

### 5. Arrancar e instalar Ubuntu 24.04 Server

```powershell
VBoxManage startvm "VM-01-extraccion" --type gui
VBoxManage startvm "VM-02-orquestacion" --type gui
```

**Por GUI:** seleccionar la VM en el panel izquierdo → botón **Iniciar**
(flecha verde) en la barra superior — equivalente exacto a `startvm --type
gui`. Antes de iniciar, asegurarse de que la ISO de Ubuntu esté conectada:
Configuración → Almacenamiento → controlador SATA → ícono de disco → elegir
la imagen `ubuntu-24.04-live-server-amd64.iso`.

Instalación estándar del instalador de Ubuntu Server (Subiquity); valores
por defecto sirven, salvo:

- Habilitar **OpenSSH server** cuando el instalador lo pregunte (evita el
  paso manual equivalente más abajo, en "VM-01: extracción", punto 6).
- No es necesario fijar la red durante la instalación -- Ubuntu detecta
  ambos adaptadores; la IP estática se asigna después (paso 6).

### 6. IP estática dentro de la red host-only

En **cada VM**, identificar la interfaz host-only con `ip a` (normalmente
`enp0s8` en VM-01, que tiene 2 NICs; `enp0s3` en VM-02, donde la host-only
es la NIC1) y editar su netplan:

```bash
sudo nano /etc/netplan/50-cloud-init.yaml
```

```yaml
network:
  ethernets:
    enp0s8:          # ajustar al nombre real de la interfaz host-only
      addresses: [192.168.56.10/24]   # .10 en VM-01, .11 en VM-02
  version: 2
```

```bash
sudo netplan apply
```

> **Nota GUI / CLI:** este paso es a nivel de Ubuntu — ocurre dentro de la
> terminal de la VM, sin importar cómo se creó la VM (GUI o CLI de
> VirtualBox). El proceso es idéntico en ambos casos.

Con esto, VM-02 ya puede llegar a VM-01 por `192.168.56.10` (la IP que se
usa más abajo en "Llave SSH hacia VM-01" y en el checklist final), y el
resto de esta guía aplica igual desde aquí.

**Modo alterno sin LAN/VPN real:** si en este punto no hay forma de
alcanzar el origen MSSQL desde VM-01 (sin red privada ni VPN disponibles),
la alternativa validada es levantar SQL Server en un contenedor Docker con
datos sintéticos dentro de la propia VM-01.

## VM-01: extracción (dlt)

1. **Clonar el repo:**

   ```bash
   git clone <url-del-repo> /opt/dlt-medallion-pipeline
   cd /opt/dlt-medallion-pipeline
   ```

2. **Driver ODBC para SQL Server** (`pyodbc` lo necesita a nivel de sistema,
   ver `docs/COMMANDS-PIPELINE.md` sección 2). En Ubuntu 24.04, repositorio
   oficial de Microsoft:

   ```bash
   curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
   # Si packages.microsoft.com todavía no publica un repo "24.04" específico
   # (puede tardar tras un release de Ubuntu), usar el de 22.04 -- es
   # compatible, verificar la lista disponible en packages.microsoft.com/config/ubuntu/
   curl https://packages.microsoft.com/config/ubuntu/24.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
   sudo apt-get update
   sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
   ```

3. **Entorno Python** (igual que en desarrollo local, ver
   `docs/COMMANDS-PIPELINE.md` secciones 1-2):

   ```bash
   python3 -m venv dlt_env
   source dlt_env/bin/activate
   pip install -r requirements.txt
   ```

4. **ADC propio de VM-01** (cuenta personal del usuario en el laboratorio
   -- en producción real sobre GCE esto se resuelve solo, sin este paso,
   vía la service account adjunta a la instancia):

   ```bash
   sudo apt-get install -y apt-transport-https ca-certificates gnupg curl
   curl -sSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
   echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
   sudo apt-get update && sudo apt-get install -y google-cloud-cli
   gcloud auth login
   gcloud config set project <PROJECT_ID>
   gcloud auth application-default login
   ```

5. **Secretos**: `cp .dlt/secrets.toml.example .dlt/secrets.toml` y
   `cp .env.example .env`, completar con los valores reales de esta VM (ver
   `docs/COMMANDS-PIPELINE.md` secciones 4 y 6 para el detalle de cada
   campo).

6. **Servidor SSH** (para que VM-02 dispare la extracción vía
   `SSHOperator`):

   ```bash
   sudo apt-get install -y openssh-server
   sudo systemctl enable --now ssh
   ```

7. **Verificación:**

   ```bash
   python scripts/smoke_test_connection.py
   python run_pipeline.py --manifest sources/business_partners.yaml
   ```

## VM-02: orquestación (Airflow + dbt)

1. **Clonar el repo** (mismo paso que VM-01, punto 1).

2. **Docker Engine + plugin compose** (repositorio oficial de Docker):

   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   sudo usermod -aG docker "$USER"   # cerrar sesión y volver a entrar para que aplique
   ```

3. **ADC propio de VM-02** (otra cuenta/login independiente del de VM-01,
   mismos pasos de instalación de `gcloud` que en VM-01 punto 4, pero
   corriendo `gcloud auth application-default login` aquí -- la ruta que
   genera es la que va en `GOOGLE_APPLICATION_CREDENTIALS` del `.env` de
   **esta** VM).

4. **Llave SSH hacia VM-01** (generarla en VM-02, copiar la pública a
   VM-01 -- nunca al revés):

   ```bash
   ssh-keygen -t ed25519 -f ./airflow/keys/vm01_id_rsa -C "airflow-vm02-to-vm01" -N ""
   ssh-copy-id -i ./airflow/keys/vm01_id_rsa.pub <usuario>@<ip-vm01>
   # si ssh-copy-id no está disponible: copiar el contenido de
   # vm01_id_rsa.pub a mano dentro de ~/.ssh/authorized_keys en VM-01
   ```

5. **Variables de entorno y arranque del stack**: seguir
   `docs/COMMANDS-PIPELINE.md` sección 11 desde el paso 1 (`.env`,
   `AIRFLOW_FERNET_KEY`, `docker compose up`) hasta el final (creación de
   la `Connection` SSH `vm01_extraccion` en Airflow usando la llave del
   punto 4).

## Diferencias laboratorio (VirtualBox) vs producción (GCP)

| Aspecto | Laboratorio (VirtualBox) | Producción (GCE real) |
| --- | --- | --- |
| Red entre VMs | Adaptador Bridged (VM-01, hereda LAN/VPN del host) + Host-only (VM-01↔VM-02) | VPC real de GCP, reglas de firewall por IP interna |
| ADC | `gcloud auth application-default login` manual por VM, cuenta personal | Service account adjunta a la instancia GCE, ADC automático vía metadata server, sin login manual |
| Service accounts | No son necesarias (el usuario es Admin de su propio proyecto de prueba) | 2 SAs dedicadas con permisos acotados (una por VM, alcance mínimo: bronze-write en VM-01, staging/curated-write en VM-02) |
| Origen MSSQL | Red privada/VPN desde el host, o contenedor Docker con SQL Server para modo aislado | Conectividad de red definida por la topología de red que se elija en producción |

Para la checklist de la capa de datos (no infraestructura): `docs/COMMANDS-PIPELINE.md` sección "Checklist para migrar a producción".

## Checklist de verificación end-to-end

- [ ] Desde VM-02: `ssh -i airflow/keys/vm01_id_rsa <usuario>@<ip-vm01>` conecta sin pedir password.
- [ ] `docker compose exec airflow-webserver airflow dags list` muestra `business_partners_pipeline`.
- [ ] Disparo manual de `business_partners_pipeline` desde la UI de Airflow corre las 3 fases (`extract_bronze` → `transform_staging` → `transform_curated`) sin error.
- [ ] Un dominio "solo bronze" nuevo (sin `dbt/models/staging/<dominio>/`, ver el ejemplo `orders` en `docs/ARCHITECTURE.md`) corre solo `extract_bronze` — comportamiento esperado, no un error de configuración.
