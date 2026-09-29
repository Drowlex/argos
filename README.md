# Dagster Replicator - Use and Deployment 
>
  ## Initial
  * ``` dagster project scaffold --name dagster-argos``` 
  ### Open New Temrinal and run dagit on bash 
  * ``` dagit -h 0.0.0.0 -p 3000 ```
  ## Testing with docker-compose 🐳
  1. Start service
      * ```docker-compose up```
      * ```docker-compose up -d```
  2. Start service with limits
      * ```docker-compose --compatibility up```
      * ```docker-compose --compatibility up -d```
      * ```docker-compose -p appN up```
      * ```docker-compose --compatibility -p appN up```
      * ```docker-compose --compatibility -p appN up -d```
  3. Clean logs force
      * ```sudo truncate -s 0 $(docker inspect --format='{{.LogPath}}' dagsterTest)```
  4. Turn off service
      * ```docker-compose down -v```
  5. Rebuild the containers
      * ```docker-compose build```
  6. Limpiar ejecuciones
      * Ejecutar el comando en la raiz del proyecto
          * ```sudo chmod -R +x erase.sh```
      * Ingresar contraseña y ejecutar este comando
          * ```./erase.sh```
  ## Developers 👨‍💻🔥 
  * **Luis Ortiz @Drowlex** - *Development and Documentation* - [DKL](https://github.com/drowlex)
>
  🎉👨‍💻 _¡Sin miedo al éxito!_ 👨‍💻🎉    

