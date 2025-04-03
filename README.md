# vhost-finder
Herramienta escrita en python para descubrir subdominios, específicamente orientada a descubrir subdominios en una red privada con servidor DNS privado donde solo podemos acceder a nuevos subdominios si sabemos de antemano que servidor DNS usar o si agregamos el subdominio en el /etc/hosts.


Uso:

python3 vhost-finder.py &lt;IP objetivo&gt; &lt;dominio base objetivo&gt; &lt;diccionario de subdominios&gt; [opciones]

Opciones:
--insecure : para usar http en lugar de https

Ejemplo de uso:

python3 vhost-finder.py 10.20.14.18 dominio.com /usr/share/seclists/Discovery/DNS/subdomains-top1million-110000.txt --insecure
