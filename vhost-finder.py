#!/usr/bin/env python3

import os
import requests
import sys
import signal
import shutil
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import Fore, Back, Style

# Configuración global
hosts_rute = "/etc/hosts"
hosts_backup = "/etc/hosts.bak"
MAX_THREADS = 20  # Número máximo de hilos concurrentes

#-------------------------[COMPROBACIÓN DE USO CORRECTO]----------------------------

def check_usage():
    if len(sys.argv) <= 3:
        print(Style.BRIGHT + "Usage: " + sys.argv[0] + " <target IP> <target domain> <dict> [options]")
        print("\nOptions:\n\n" + Fore.BLUE + "--insecure:" + Fore.RESET + " use http instead https" + Style.RESET_ALL)
        sys.exit(1)

#--------------------------------[VALIDACIÓN DE IP]--------------------------------

def es_ip_valida(ip):
    patron = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if not patron.match(ip):
        return False

    try:
        octetos = ip.split('.')
        for octeto in octetos:
            if not 0 <= int(octeto) <= 255:
                return False
    except ValueError:
        return False

    return True

#--------------------------[MANEJO DE COPIA DE SEGURIDAD]----------------------------

def make_backup():
    if os.path.exists(hosts_rute):
        print(Fore.YELLOW + "\n[..] Creando copia de seguridad del archivo hosts" + Style.RESET_ALL)
        print(Fore.WHITE + Back.RED + "[W] No cancele la ejecución hasta terminar!" + Style.RESET_ALL)
        try:
            shutil.copy(hosts_rute, hosts_backup)
            print(Fore.GREEN + "[+] Salva creada satisfactoriamente" + Style.RESET_ALL)
        except IOError as e:
            print(Fore.RED + f"[!] Error al crear copia: {e}" + Style.RESET_ALL)
            sys.exit(1)
    else:
        print(Fore.RED + "[!] No se encontró el archivo /etc/hosts." + Style.RESET_ALL)
        sys.exit(1)

def restore_backup(signal_received=None, frame=None, status=0):
    if os.path.exists(hosts_backup):
        print(Fore.YELLOW + "\n[..] Restaurando el archivo hosts original..." + Style.RESET_ALL)
        try:
            shutil.copy(hosts_backup, hosts_rute)
            os.remove(hosts_backup)
            print(Fore.GREEN + "[+] Archivo hosts restaurado" + Style.RESET_ALL)
            sys.exit(status)
        except IOError as e:
            print(Fore.RED + f"[!] Error al restaurar: {e}" + Style.RESET_ALL)
        finally:
            sys.exit(status)
    else:
        print(Fore.RED + "[!] No se encontró la copia de seguridad." + Style.RESET_ALL)
        sys.exit(1)

#-----------------------------[OBTENER LÍNEA BASE]------------------------------------

def get_baseline(IP, domain, protocol):
    try:
        with open(hosts_rute, "a") as f:
            f.write(f"{IP} {domain}\n")
        
        response = requests.get(f"{protocol}{domain}", timeout=10)
        content = response.text
        return len(content), len(content.split())
    except requests.RequestException as e:
        print(Fore.RED + f"[!] Error en solicitud base: {e}" + Style.RESET_ALL)
        restore_backup(status=1)

#-------------------------------[CONFIGURACIÓN INICIAL]-------------------------------

def setup_environment():
    # Verificar uso correcto al inicio
    if len(sys.argv) <= 3:
        check_usage()
    
    IP = sys.argv[1]
    if not es_ip_valida(IP):
        print(Fore.WHITE + Back.RED + "La dirección IP introducida no es válida" + Style.RESET_ALL)
        sys.exit(1)
    
    protocol = "https://"
    if "--insecure" in sys.argv:
        protocol = "http://"
    
    domain = sys.argv[2]
    dict_file = sys.argv[3]
    
    if not os.path.exists(dict_file):
        print(Fore.WHITE + Back.RED + "El diccionario especificado no existe" + Style.RESET_ALL)
        sys.exit(1)
    
    return IP, protocol, domain, dict_file

#-----------------------------[PROCESAR SUBDOMINIO]-----------------------------------

def check_subdomain(subdomain, protocol, domain, base_words, IP):
    url = f"{protocol}{subdomain}.{domain}"
    full_subdomain = f"{subdomain}.{domain}"
    
    try:
        # Escribir en hosts una vez por subdominio
        shutil.copy(hosts_backup, hosts_rute)
        with open(hosts_rute, "a") as h:
            h.write(f"{IP} {full_subdomain}\n")
        
        # Realizar la solicitud HTTP
        with requests.Session() as session:
            response = session.get(url, timeout=10)
            
            if response.status_code not in [404,500]:
                contenido = response.text
                num_words = len(contenido.split())
                if num_words != base_words:
                    return (url, response.status_code)
    
    except requests.RequestException:
        pass  # Ignorar errores de conexión/timeout
    except Exception as e:
        sys.exit(1)
    
    return None

#----------------------------------[BARRA DE PROGRESO]--------------------------------
def print_progress(current, total, bar_length=50):
    percent = float(current) * 100 / total
    arrow = '-' * int(percent/100 * bar_length - 1) + '>'
    spaces = ' ' * (bar_length - len(arrow))
    
    sys.stdout.write(Fore.BLUE + f"\rProgress: [{arrow}{spaces}] {percent:.2f}% ({current}/{total})" + Fore.RESET)
    sys.stdout.flush()

#----------------------------------[DESCUBRIMIENTO]-----------------------------------

def discover(base_char, base_words, IP, protocol, domain, dict_file):
    discovered = []
    
    # Primero contamos el número total de líneas en el diccionario
    with open(dict_file, "r") as dictionary:
        total_lines = sum(1 for _ in dictionary)
    
    processed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        
        with open(dict_file, "r") as dictionary:
            for line in dictionary:
                subdomain = line.strip()
                if subdomain:  # Ignorar líneas vacías
                    futures.append(
                        executor.submit(
                            check_subdomain, 
                            subdomain, 
                            protocol, 
                            domain,
                            base_words,
                            IP
                        )
                    )
        
        for future in as_completed(futures):
            result = future.result()
            processed += 1
            print_progress(processed, total_lines)
            
            if result:
                url, status = result
                # Mover a nueva línea para mostrar el descubrimiento
                print(f"\nDiscovered: {Fore.GREEN}{url}{Fore.RESET} status code: {status}")
                discovered.append(url)
    
    print()  # Nueva línea al finalizar
    return discovered

#----------------------------------[FLUJO PRINCIPAL]----------------------------------

def main():
    signal.signal(signal.SIGINT, restore_backup)
    
    # Verificar argumentos antes de continuar
    if len(sys.argv) <= 3:
        check_usage()
        return
    
    IP, protocol, domain, dict_file = setup_environment()
    make_backup()
    
    base_char, base_words = get_baseline(IP, domain, protocol)
    print(f"\n[+] Baseline established: {base_words} words, {base_char} chars")
    
    print(Fore.YELLOW + "\n[..] Starting subdomain discovery..." + Style.RESET_ALL)
    discovered = discover(base_char, base_words, IP, protocol, domain, dict_file)
    
    print(Fore.GREEN + f"\n[+] Found {len(discovered)} subdomains" + Style.RESET_ALL)
    restore_backup(status=0)

if __name__ == "__main__":
    main()