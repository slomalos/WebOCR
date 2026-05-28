package config

import (
	"fmt"
	"log"

	amqp "github.com/rabbitmq/amqp091-go"
)

var RabbitConn *amqp.Connection
var RabbitChannel *amqp.Channel

func InitRabbitMQ() {
	var err error
	RabbitConn, err = amqp.Dial("amqp://guest:guest@localhost:5672/")
	if err != nil {
		log.Fatal("[!] Ошибка RabbitMQ: ", err)
	}
	RabbitChannel, err = RabbitConn.Channel()
	if err != nil {
		log.Fatal("[!] Ошибка канала RabbitMQ: ", err)
	}
	_, err = RabbitChannel.QueueDeclare("ocr_tasks", true, false, false, false, nil)
	if err != nil {
		log.Fatal("[!] Ошибка очереди: ", err)
	}
	fmt.Println("[*] Подключение к RabbitMQ успешно!")
}